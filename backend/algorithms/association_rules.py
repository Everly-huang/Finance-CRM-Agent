import itertools
from collections import defaultdict
from database.db_connection import get_customer_records, get_financial_products


def recommend_by_association(target_product_name, min_support=0.2, min_confidence=0.5, top_k=6):
    """
    基于关联规则的推荐算法
    :param target_product_name: 目标产品名称
    :param min_support: 最小支持度阈值
    :param min_confidence: 最小置信度阈值
    :param top_k: 返回推荐数量
    :return: 推荐产品列表
    """

    # 1. 获取历史购买记录
    customer_records = get_customer_records()

    if not customer_records:
        return get_fallback_recommendations(top_k)

    # 2. 构建事务数据库
    transactions = build_transactions(customer_records)

    if not transactions:
        return get_fallback_recommendations(top_k)

    # 3. 计算频繁项集
    frequent_itemsets = find_frequent_itemsets(transactions, min_support)

    # 4. 生成关联规则并计算置信度
    association_rules = generate_association_rules(frequent_itemsets, transactions, min_confidence)

    # 5. 为目标产品寻找关联推荐
    recommendations = find_associated_products(target_product_name, association_rules, top_k)

    # 6. 如果关联推荐不足，用热门产品补充
    if len(recommendations) < top_k:
        recommendations.extend(get_fallback_recommendations(top_k - len(recommendations)))

    return recommendations[:top_k]


def build_transactions(customer_records):
    """构建事务数据库：每个客户购买的产品集合"""
    transactions_dict = defaultdict(set)

    for record in customer_records:
        customer_id = record['customer_id']
        product_name = record['product_name']
        transactions_dict[customer_id].add(product_name)

    return [list(products) for products in transactions_dict.values() if len(products) > 1]


def find_frequent_itemsets(transactions, min_support):
    """使用Apriori算法找出频繁项集"""
    # 计算单个产品的支持度
    item_counts = defaultdict(int)
    for transaction in transactions:
        for item in transaction:
            item_counts[item] += 1

    num_transactions = len(transactions)
    frequent_1_itemsets = {}

    for item, count in item_counts.items():
        support = count / num_transactions
        if support >= min_support:
            frequent_1_itemsets[frozenset([item])] = support

    frequent_itemsets = frequent_1_itemsets.copy()
    current_itemsets = frequent_1_itemsets

    k = 2
    while current_itemsets:
        # 生成候选k项集
        candidate_itemsets = generate_candidates(current_itemsets, k - 1)

        # 计算候选k项集的支持度
        itemset_counts = defaultdict(int)
        for transaction in transactions:
            transaction_set = set(transaction)
            for itemset in candidate_itemsets:
                if itemset.issubset(transaction_set):
                    itemset_counts[itemset] += 1

        # 筛选频繁k项集
        current_itemsets = {}
        for itemset, count in itemset_counts.items():
            support = count / num_transactions
            if support >= min_support:
                current_itemsets[itemset] = support

        frequent_itemsets.update(current_itemsets)
        k += 1

    return frequent_itemsets


def generate_candidates(prev_itemsets, k):
    """生成候选k项集"""
    candidates = set()
    itemsets_list = list(prev_itemsets.keys())

    for i in range(len(itemsets_list)):
        for j in range(i + 1, len(itemsets_list)):
            itemset1 = itemsets_list[i]
            itemset2 = itemsets_list[j]

            # 检查前k-1项是否相同
            if len(itemset1) != k or len(itemset2) != k:
                continue

            list1 = sorted(list(itemset1))
            list2 = sorted(list(itemset2))

            if list1[:-1] == list2[:-1]:
                new_itemset = itemset1.union(itemset2)
                candidates.add(new_itemset)

    return candidates


def generate_association_rules(frequent_itemsets, transactions, min_confidence):
    """生成关联规则并计算置信度"""
    rules = []
    num_transactions = len(transactions)

    for itemset, support in frequent_itemsets.items():
        if len(itemset) < 2:
            continue

        # 生成所有可能的规则
        itemset_list = list(itemset)
        for i in range(1, len(itemset_list)):
            for antecedent in itertools.combinations(itemset_list, i):
                antecedent_set = frozenset(antecedent)
                consequent_set = itemset - antecedent_set

                # 计算置信度
                antecedent_count = count_itemset_occurrence(antecedent_set, transactions)
                if antecedent_count > 0:
                    confidence = (support * num_transactions) / antecedent_count

                    if confidence >= min_confidence:
                        rules.append({
                            'antecedent': antecedent_set,
                            'consequent': consequent_set,
                            'support': support,
                            'confidence': confidence,
                            'lift': confidence / (
                                        count_itemset_occurrence(consequent_set, transactions) / num_transactions)
                        })

    return rules


def count_itemset_occurrence(itemset, transactions):
    """计算项集在事务中出现的次数"""
    count = 0
    for transaction in transactions:
        if itemset.issubset(set(transaction)):
            count += 1
    return count


def find_associated_products(target_product_name, association_rules, top_k):
    """为目标产品寻找关联推荐"""
    recommendations = []

    for rule in association_rules:
        antecedent = rule['antecedent']
        consequent = rule['consequent']

        # 如果目标产品在前件中，推荐后件产品
        if target_product_name in antecedent and len(consequent) == 1:
            recommended_product = list(consequent)[0]
            if recommended_product != target_product_name:
                product_info = get_product_info(recommended_product)
                if product_info:
                    recommendations.append({
                        **product_info,
                        'recommend_type': '关联推荐',
                        'support': f"{rule['support']:.2%}",
                        'confidence': f"{rule['confidence']:.2%}",
                        'association_score': rule['confidence'] * rule['support']
                    })

    # 按关联度分数排序
    recommendations.sort(key=lambda x: x['association_score'], reverse=True)

    # 移除重复产品
    seen_products = set()
    unique_recommendations = []
    for rec in recommendations:
        if rec['name'] not in seen_products:
            seen_products.add(rec['name'])
            unique_recommendations.append(rec)

    return unique_recommendations[:top_k]


def get_product_info(product_name):
    """获取产品详细信息"""
    products = get_financial_products()
    for product in products:
        if product['name'] == product_name:
            return {
                'id': product['id'],
                'name': product['name'],
                'category_id': product['category_id'],
                'price': product['price'],
                'risk_level': product['risk_level'],
                'expected_return': product['expected_return'],
                'description': product['description']
            }
    return None


def get_fallback_recommendations(top_k):
    """获取备选推荐（当关联推荐不足时使用）"""
    products = get_financial_products()
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


def recommend_products_by_association(selected_product_id, top_k=6):
    """
    新的接口函数，接收产品ID而不是产品名称
    与最近邻算法保持一致的接口
    """
    # 1. 获取所有产品
    all_products = get_financial_products()
    
    # 2. 根据ID找到产品名称
    target_product_name = None
    for product in all_products:
        if product['id'] == selected_product_id:
            target_product_name = product['name']
            break
    
    if not target_product_name:
        return get_fallback_recommendations(top_k)
    
    # 3. 调用原有的关联规则算法
    recommendations = recommend_by_association(target_product_name, top_k=top_k)
    
    return recommendations