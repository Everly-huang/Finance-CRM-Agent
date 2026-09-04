import math
from database.db_connection import get_financial_products,add_customer_input

def recommend_products(target_category, target_price, top_k=6):
    """
    最近邻推荐算法
    """
    products = get_financial_products()
    
    if not products:
        return []
    
    category_ids = [p['category_id'] for p in products]
    prices = [p['price'] for p in products]
    
    min_category = min(category_ids)
    max_category = max(category_ids)
    min_price = min(prices)
    max_price = max(prices)
    
    # 调整超出范围的输入值
    adjusted_category = max(min_category, min(target_category, max_category))
    adjusted_price = max(min_price, min(target_price, max_price))
    
    min_distance = float('inf')
    is_abnormal = 0
    
    max_cat_diff = max_category - min_category if max_category != min_category else 1
    max_price_diff = max_price - min_price if max_price != min_price else 1
    
    for product in products:
        # 计算绝对差异
        cat_abs_diff = abs(adjusted_category - product['category_id'])
        price_abs_diff = abs(adjusted_price - product['price'])
        
        # 归一化差异
        norm_cat_diff = cat_abs_diff / max_cat_diff
        norm_price_diff = price_abs_diff / max_price_diff
        
        # 计算欧几里得距离
        cat_weight = 0.4
        price_weight = 0.6
        
        cat_diff = norm_cat_diff * cat_weight
        price_diff = norm_price_diff * price_weight
        distance = math.sqrt(cat_diff ** 2 + price_diff ** 2)
        
        product['distance'] = distance
        product['similarity'] = 1 / (1 + distance)
        
        if distance < min_distance:
            min_distance = distance
    
    if min_distance > 0.3:
        is_abnormal = 1
        recommendations = get_popular_products(products, top_k)
    else:
        is_abnormal = 0
        recommendations = get_similar_products(products, top_k)
    
    try:
        add_customer_input(
            preferred_category=target_category,
            investment_amount=target_price,
            min_distance=min_distance,
            is_abnormal=is_abnormal
        )
        print(f"已保存客户输入数据：类别={target_category}, 金额={target_price}, 最小距离={min_distance:.4f}, 异常={is_abnormal}")
    except Exception as e:
        print(f"保存客户输入数据失败: {e}")
    
    return recommendations

def get_similar_products(products, top_k):
    """基于相似性推荐"""
    sorted_products = sorted(products, key=lambda x: x['similarity'], reverse=True)
    
    recommendations = []
    for product in sorted_products[:top_k]:
        recommendations.append({
            'id': product['id'],
            'name': product['name'],
            'category_id': product['category_id'],
            'price': product['price'],
            'risk_level': product['risk_level'],
            'expected_return': product['expected_return'],
            'description': product['description'],
            'recommend_type': '相似推荐'
        })
    
    return recommendations

def get_popular_products(products, top_k):
    """推荐热门商品"""
    sorted_products = sorted(products, key=lambda x: x['expected_return'], reverse=True)
    
    recommendations = []
    for product in sorted_products[:top_k]:
        recommendations.append({
            'id': product['id'],
            'name': product['name'],
            'category_id': product['category_id'],
            'price': product['price'],
            'risk_level': product['risk_level'],
            'expected_return': product['expected_return'],
            'description': product['description'],
            'recommend_type': '热门推荐'
        })
    
    return recommendations