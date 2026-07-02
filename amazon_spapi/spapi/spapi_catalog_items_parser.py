import json

from pint import UnitRegistry

from amazon_spapi.log import logger


class SpapiCatalogItemsParser():
  ureg = UnitRegistry()
  dimentions_name = ['weight', 'width', 'length', 'height']
  dimention_units = {
    'weight': 'lbs',
    'width': 'inch',
    'length': 'inch',
    'height': 'inch',
  }
  product_flat_attrs = [
    'asin', 'dimensions', 'identifiers', 'productTypes',
    'relationships', 'salesRanks', 'summaries', 'classifications'
  ]
  has_value_array_attrs_in_summary = ['edition', 'manufacturer', 'publication_date']
  has_value_array_attrs_in_attributes = ['binding', 'pages']
  array_attrs_in_attributes = ['item_dimensions', 'item_package_dimensions']
  invalid_categories = ['Products', 'Categories', 'Departments', 'Styles', 'Subjects']


  @classmethod
  def parse(cls, response):
    d = dict()
    product_dicts = {}
    parsed_resp = response.payload
    results = parsed_resp.get('items', None)
    if not results:
      return product_dicts

    for product_dict in results:
      if "Error" in product_dict:
        logger.warning(
          '[SPAPIError] %s', product_dict['Error'].get('Message', d).get('value', ''))
        continue

      attributes = product_dict.get('attributes', d)

      product = {}

      for attr in cls.product_flat_attrs:
        product[attr] = product_dict.get(attr)

      product['attributes'] = cls.remove_items_exceed_level(product_dict.get('attributes', d), 5)

      images = []
      for img in product_dict['images'][0]['images']:
        images.append(img['link'])

      try:
        title = attributes.get('item_name', [{}])[0].get('value', '')[:255]
        brand = attributes.get('brand', [{}])[0].get('value', '')[:100]
        format = ""

        categories = cls.get_categories(product_dict.get('classifications'))
        top_category = second_category = third_category = None
        if categories:
          cats = list(categories)
          cat = cats.pop(0)
          if cat:
            top_category = cat['cat_name']

          if cats:
            cat = cats.pop(0)
            if cat:
              second_category = cat['cat_name']

          if cats:
            cat = cats.pop(0)
            if cat:
              third_category = cat['cat_name']

        try:
          sales_ranking = int(product.get('salesRanks', [{}])[0]
            .get('displayGroupRanks', [{}])[0].get('rank', 0))
        except:
          sales_ranking = 0

        dimension = {}
        dimensions = product.get('dimensions', [])
        lwh = 0
        weight = None
        if isinstance(dimensions, list) and len(dimensions) > 0 and isinstance(dimensions[0], dict):
          di = dimensions[0]
          dimension = {
            dimension_name: cls.get_dimension_value(di, dimension_name)
            for dimension_name in cls.dimention_units
          }

          weight = dimension.pop('weight', 0)
          edges = [
            float(dimension[k])
            for k in ('length', 'width', 'height')
            if dimension.get(k)
          ]
          lwh = int(round(max(edges))) if edges else 0

        ranks = []
        rank_types = ['classificationRanks', 'displayGroupRanks']
        for rank in product.get('salesRanks', []):
          for rank_type in rank_types:
            for rank_dict in rank.get(rank_type, []):
              ranks.append({
                'category': rank_dict.get('title', ''),
                'rank': rank_dict.get('rank', '')
              })

        asin = product['asin']
        product_dicts[asin] = {
          'asin': asin,
          'title': title,
          'brand': brand,
          'weight': weight,
          'format': format,
          'sales_rank': sales_ranking,
          'lwh': lwh,
          'sales_ranks': ranks,
          'images': images,
          'top_category': top_category,
          'second_category': second_category,
          'third_category': third_category,
          'categories': categories,
          **product
        }

        for attr in cls.has_value_array_attrs_in_attributes:
          product_dicts[asin][attr] = attributes.get(attr, [{}])[0].get('value', None)

        for attr in cls.array_attrs_in_attributes:
          product_dicts[asin][attr] = attributes.get(attr, [{}])[0]

        product_dicts[asin]['item_weight'] = cls.get_weight_from_attributes('item_weight', attributes)
        product_dicts[asin]['item_package_weight'] = cls.get_weight_from_attributes('item_package_weight', attributes)

        if 'subject_keyword' in attributes:
          product_dicts[asin]['subject_keyword'] = [subject['value'] for subject in attributes['subject_keyword']]

        if 'generic_keyword' in attributes:
          product_dicts[asin]['generic_keyword'] = [subject['value'] for subject in attributes['generic_keyword']]

        product_dicts[asin]['item_dimensions'] = attributes.get('item_dimensions', [{}])[0]

        summaries = product_dicts.get('summaries', {})
        for attr in cls.has_value_array_attrs_in_summary:
          product_dicts[asin][attr] = attributes.get(attr, [{}])[0].get('value', None)

        if 'list_price' in summaries:
          product_dicts[asin]['list_price'] = {'currency': attributes['list_price'][0]['currency'], 'value': attributes['list_price'][0]['value']}
      except Exception as e:
        logger.exception(e)

    return product_dicts

  @classmethod
  def get_dimension_value(cls, dimension_obj, dimension_name):
    packaege_or_item_dimension = dimension_obj.get('package', dimension_obj.get('item', {})).get(dimension_name, {})
    if not packaege_or_item_dimension.get('value'):
      return 0

    value_with_unit = '{} {}'.format(packaege_or_item_dimension.get('value', 0), packaege_or_item_dimension.get('unit', ''))
    return round(cls.ureg(value_with_unit).to(cls.dimention_units.get(dimension_name)).m, 2)

  @classmethod
  def get_weight_from_attributes(cls, attr, attributes):
    weight = attributes.get(attr, [{}])[0]
    if not weight.get('value'):
      return 0

    weight_value = float(weight.get('value', 0))

    weight_unit = weight.get('unit', 'pound')
    if weight_unit == 'hundredths_pounds':
      weight_value = weight_value * 0.01
      weight_unit = 'pound'

    weight_value_with_unit = '{} {}'.format(weight_value, weight_unit)
    return round(cls.ureg(weight_value_with_unit).to(cls.dimention_units.get('weight')).m, 2)

  @classmethod
  def remove_items_exceed_level(cls, data, n, current_level=0):
    """
    Recursively removes items exceeding level n in a deeply nested dictionary or list.
    """
    if current_level >= n:
      return None  # Or any other placeholder you prefer

    if isinstance(data, dict):
      new_dict = {}
      for key, value in data.items():
        processed_value = cls.remove_items_exceed_level(value, n, current_level + 1)
        if processed_value is not None:
          new_dict[key] = processed_value

      return new_dict
    elif isinstance(data, list):
      new_list = []
      for item in data:
        processed_item = cls.remove_items_exceed_level(item, n, current_level + 1)
        if processed_item is not None:
          new_list.append(processed_item)

      return new_list
    else:
      return data  # Return non-container types directly

  @classmethod
  def get_categories(cls, classifications):
    if not classifications:
      return

    try:
      classifications_ = classifications[0]
      cs = classifications_.get('classifications', {})
      if not cs:
        return

      cs_names = []
      cs = cs[0]
      while cs:
        cs_name = cs.get('displayName', '')
        cs_id = cs.get('classificationId', '')
        if not cs_name or not cs_id or cs_name in cls.invalid_categories:
          cs_parent = cs.get('parent', None)
          if cs_parent:
            cs = cs_parent
          else:
            cs = None

          continue

        cs_names.append({'cat_name': cs_name, 'cat_id': cs_id})
        cs_parent = cs.get('parent', None)
        if cs_parent:
          cs = cs_parent
        else:
          cs = None

      cs_names.reverse()

      return cs_names
    except Exception as e:
      logger.exception(e)
