import copy
import time
import sys
import json

from elasticsearch import Elasticsearch
from elasticsearch import helpers
from elasticsearch.client import IndicesClient
from elasticsearch.exceptions import RequestError
from elasticsearch.exceptions import NotFoundError
from elasticsearch.exceptions import ConnectionTimeout
from elasticsearch.exceptions import ConnectionError
from elasticsearch.exceptions import SSLError
from elasticsearch.exceptions import TransportError
from elasticsearch.exceptions import ElasticsearchException

from amazon_spapi.services.elasticsearch import es_retry

from amazon_spapi.log import logger

# Default HTTP timeout (seconds) for ES 7.x scroll/search; urllib3 default is 10s.
DEFAULT_ES_TIMEOUT = 60


class ProductService(object):
  def __init__(self, host, port, user, password, max_retry=3, timeout=DEFAULT_ES_TIMEOUT):
    self.host = host
    self.port = port
    self.user = user
    self.password = password
    self.max_retry = max_retry
    self.timeout = timeout

    self.esclient = Elasticsearch(
      hosts=host,
      port=port,
      http_auth=(user, password),
      timeout=timeout,
      retry_on_timeout=True,
    )

  def _needs_shard_defaults(self, settings_section):
    if not isinstance(settings_section, dict):
      return True
    if "number_of_shards" in settings_section or "number_of_replicas" in settings_section:
      return False
    idx = settings_section.get("index")
    if isinstance(idx, dict) and (
        "number_of_shards" in idx or "number_of_replicas" in idx
    ):
      return False
    return True

  def _apply_default_shard_settings(self, body):
    """Use one primary and no replicas unless caller set shard/replica counts (saves cluster shard budget)."""
    body = copy.deepcopy(body) if body else {}
    body.setdefault("settings", {})
    s = body["settings"]
    if self._needs_shard_defaults(s):
      s["number_of_shards"] = 1
      s["number_of_replicas"] = 0
    return body

  def index_exists(self, indice_name):
    try:
      return bool(self.esclient.indices.exists(index=indice_name))
    except Exception:
      return False

  def ensure_indice(self, indice_name, settings=None):
    ic = IndicesClient(self.esclient)
    if ic.exists(indice_name):
      if settings and settings.get("mappings"):
        try:
          ic.put_mapping(body=settings["mappings"], index=indice_name)
        except (RequestError, TransportError) as e:
          logger.debug("put_mapping skipped for %s: %s", indice_name, e)
      return True

    create_body = self._apply_default_shard_settings(settings)
    try:
      ic.create(indice_name, body=create_body)
    except RequestError as e:
      logger.warning(
        "Could not create Elasticsearch index %s: %s",
        indice_name,
        e,
      )
      return False

    return ic.exists(indice_name)

  def search_products(self, indice_name, product_ids, options={}):
    if not isinstance(product_ids, list):
      product_ids = [product_ids]

    query = {"terms": {"_id": product_ids}}

    params = {
      'index': indice_name,
      'from_': 0,
      'size': len(product_ids),
      'body': {
        'query': query
      }
    }
    if options:
        params.update(options)

    wrapped_search = es_retry(self.esclient.search)
    resp = None
    try:
      resp = wrapped_search(**params)
    except:
      pass

    if resp is None:
      result = None
    elif resp == -1:
      result = False
    else:
      result = {}
      if "hits" in resp['hits']:
          for item in resp['hits']['hits']:
            result[item['_id']] = item['_source']

    return result

  def is_product_exist(self, indice_name, product_ids):
    if not isinstance(product_ids, list):
      product_ids = [product_ids]

    query = {"terms": {"_id": product_ids}}

    params = {
      'index': indice_name,
      'from_': 0,
      'size': len(product_ids),
      '_source': False,
      'body': {
        'query': query
      }
    }

    wrapped_search = es_retry(self.esclient.search)
    resp = None
    try:
      resp = wrapped_search(**params)
    except:
      pass

    if resp is None:
      result = None
    elif resp == -1:
      result = False
    else:
      result = {pid:False for pid in product_ids}
      if "hits" in resp['hits']:
          for item in resp['hits']['hits']:
            result[item['_id']] = True

    return result

  def custom_search(self, indice_name, options, from_=0, size=1000):
    params = {
      'index': indice_name,
      'from_': from_,
      'size': size,
      # 'body': {
      #   'query': query
      # }
    }
    if options:
      params.update(options)

    wrapped_search = es_retry(self.esclient.search)
    resp = None
    try:
      resp = wrapped_search(**params)
    except Exception as e:
      logger.exception(e)

    return resp

  def save_products(self, indice_name, products):
      """
      Save web crawled products to service.
      products : list
          The same as return value of search_products
      """
      if not isinstance(products, list):
        products = [products]

      service_products = []

      common_args = {
        '_op_type': 'index',
        '_index': indice_name,
        '_type': '_doc'
      }

      for product in products:
        service_product = dict()
        service_product.update(common_args)
        if 'product_id' not in product and '_id' not in product:
          continue

        if '_id' in product:
          service_product['_id'] = product.pop('_id')
        elif 'product_id' in product:
          service_product['_id'] = product['product_id']

        service_product['_source'] = product

        service_products.append(service_product)

      retry = self.max_retry
      while retry > 0:
        try:
          helpers.bulk(self.esclient, service_products, request_timeout=self.timeout)
          break
        except (ConnectionTimeout, ConnectionError, SSLError, TransportError):
          retry -= 1
          continue
        except Exception as e:
          raise e

  def save_products_upsert(self, indice_name, products, now=None):
    """
    Upsert documents while preserving ``created_at`` on updates.

    New documents receive both ``created_at`` and ``updated_at``; existing
    documents only refresh ``updated_at`` and caller-supplied fields.
    """
    from amazon_spapi.services.es_time_field import CREATED_AT, UPDATED_AT
    from amazon_spapi.services.es_doc_timestamps import utc_now, mirror_legacy_timestamp

    if not isinstance(products, list):
      products = [products]

    ts = now or utc_now()
    service_products = []
    common_args = {
      '_op_type': 'update',
      '_index': indice_name,
      '_type': '_doc',
    }

    for product in products:
      payload = dict(product)
      doc_id = payload.pop('_id', None) or payload.pop('product_id', None)
      if not doc_id:
        continue

      upsert_doc = dict(payload)
      upsert_doc.setdefault(CREATED_AT, ts)
      upsert_doc[UPDATED_AT] = ts

      update_doc = dict(payload)
      update_doc[UPDATED_AT] = ts
      update_doc.pop(CREATED_AT, None)

      from amazon_spapi.services.es_doc_timestamps import mirror_legacy_timestamp

      mirror_legacy_timestamp(upsert_doc, ts)
      mirror_legacy_timestamp(update_doc, ts)

      action = dict(common_args)
      action['_id'] = doc_id
      action['doc'] = update_doc
      action['upsert'] = upsert_doc
      service_products.append(action)

    if not service_products:
      return

    retry = self.max_retry
    while retry > 0:
      try:
        helpers.bulk(self.esclient, service_products, request_timeout=self.timeout)
        break
      except (ConnectionTimeout, ConnectionError, SSLError, TransportError):
        retry -= 1
        continue
      except Exception as e:
        raise e

  def load_products(self, indice_name, options = {}, scroll='15m'):
    params = {
      'index': indice_name,
      'doc_type': '_doc',
      'size': 1500,
      'query': {'query': {'match_all': {}}}
    }
    if options:
      params.update(options)

    wrapped_scan = es_retry(helpers.scan)
    try:
      for item in wrapped_scan(
        self.esclient,
        scroll=scroll,
        request_timeout=self.timeout,
        **params,
      ):
        record = None
        if '_source' in item and item['_source']:
          if isinstance(item['_source'], dict):
            record = item['_source']
          else:
            record = json.loads(item['_source'])

        yield (item['_id'], record)
    except NotFoundError as e:
      logger.error(
        "ES scroll context expired for index=%s (scroll=%s); "
        "use search_after for slow consumers or increase scroll keepalive",
        indice_name,
        scroll,
      )
      raise
    except Exception as e:
      logger.exception(e)
      raise

  def load_product_by_after_search(self, indice_name, cut_time="1999-01-01T00:00:00"):
    search_after_value = None

    while True:
      body = {
        "size": 1000,
        "sort": [
          {
            "time": {"order": "desc"},
          },
          {
            "_id": {"order": "desc"},
          }
        ],
        "query": {
          "range": {"time": {"gt": cut_time}}
        }
      }

      if search_after_value:
        body["search_after"] = search_after_value

      resp = self.esclient.search(index=indice_name, body=body)

      hits = resp["hits"]["hits"]
      if not hits:
        break

      for h in hits:
        product = h["_source"]
        yield product

      search_after_value = hits[-1]["sort"]

  def load_products_by_after_search(
    self,
    indice_name,
    cut_time="1999-01-01T00:00:01.722593+00:00",
    key="timestamp",
    label=None,
    label_field="label",
    marketplace=None,
    time_keys=None,
  ):
    from amazon_spapi.services.es_time_field import build_time_range_clause

    keys = list(time_keys) if time_keys else [key]
    sort_candidates = []
    for candidate in keys:
      if candidate and candidate not in sort_candidates:
        sort_candidates.append(candidate)

    last_error = None
    for sort_key in sort_candidates:
      try:
        yield from self._load_products_by_after_search_sorted(
          indice_name,
          cut_time=cut_time,
          sort_key=sort_key,
          query_keys=keys,
          label=label,
          label_field=label_field,
          marketplace=marketplace,
        )
        return
      except RequestError as exc:
        if self._is_missing_sort_mapping_error(exc):
          last_error = exc
          continue
        raise

    if last_error:
      raise last_error

    yield from self._load_products_by_after_search_sorted(
      indice_name,
      cut_time=None,
      sort_key="_doc",
      query_keys=(),
      label=label,
      label_field=label_field,
      marketplace=marketplace,
    )

  @staticmethod
  def _is_missing_sort_mapping_error(exc: RequestError) -> bool:
    message = str(exc)
    return "No mapping found for" in message and "sort on" in message

  def _load_products_by_after_search_sorted(
    self,
    indice_name,
    *,
    cut_time,
    sort_key,
    query_keys,
    label=None,
    label_field="label",
    marketplace=None,
  ):
    search_after_value = None
    mp = (marketplace or "").strip().lower() or None
    from amazon_spapi.services.es_time_field import build_time_range_clause

    while True:
      if cut_time and query_keys:
        range_clause = build_time_range_clause(cut_time, query_keys)
        must = [range_clause]
      else:
        must = [{"match_all": {}}]
      if label:
        must.append({"term": {label_field: label}})
      if mp:
        must.append({"term": {"marketplace": mp}})
      if len(must) == 1:
        query = must[0]
      else:
        query = {"bool": {"must": must}}

      if sort_key == "_doc":
        sort_spec = [{"_doc": {"order": "asc"}}]
      else:
        sort_spec = [
          {sort_key: {"order": "desc"}},
          {"_id": {"order": "desc"}},
        ]

      body = {
        "size": 1000,
        "sort": sort_spec,
        "query": query,
      }

      if search_after_value:
        body["search_after"] = search_after_value

      try:
        resp = self.esclient.search(index=indice_name, body=body)
      except NotFoundError:
        logger.warning(
          "[ProductService] index not found for scroll: %s",
          indice_name,
        )
        break

      hits = resp["hits"]["hits"]
      if not hits:
        break

      for h in hits:
        src = h.get("_source") or {}
        asin = src.get("asin")
        if not asin:
          doc_id = str(h.get("_id") or "")
          if ":" in doc_id:
            asin = doc_id.split(":", 1)[1]
          else:
            asin = doc_id
        asin = (asin or "").strip()
        if not asin:
          continue
        yield asin, src

      search_after_value = hits[-1]["sort"]

  def delete_products(self, indice_name, product_ids):
    actions = []
    for product_id in product_ids:
      actions.append({
        '_op_type': 'delete',
        '_index': indice_name,
        '_type': '_doc',
        '_id': product_id
      })

    retry = self.max_retry
    while retry > 0:
      try:
        helpers.bulk(self.esclient, actions, raise_on_error=False, request_timeout=self.timeout)
        break
      except (ConnectionTimeout, ConnectionError, SSLError, TransportError):
        retry -= 1
        continue
      except Exception as e:
        raise e
