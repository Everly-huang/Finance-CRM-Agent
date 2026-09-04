import sqlite3
import os

_database_initialized = False

def get_db_connection():
    """获取金融产品数据库连接"""
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'financial_products.db')
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_database():
    """初始化数据库和所有表"""
    global _database_initialized
    
    if _database_initialized:
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sample_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category_id INTEGER NOT NULL,
                price REAL NOT NULL,
                risk_level TEXT,
                expected_return REAL,
                description TEXT,
                is_popular BOOLEAN DEFAULT 0,
                created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customer_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                customer_name TEXT NOT NULL,
                product_name TEXT NOT NULL,
                category_id INTEGER,
                investment_amount REAL,
                created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customer_inputs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                preferred_category INTEGER NOT NULL,
                investment_amount REAL NOT NULL,
                min_distance REAL NOT NULL,
                is_abnormal INTEGER DEFAULT 0,
                created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Agent 审计日志表（DAT-01，需求文档 5.4 / 8.2：调用时间/输入/输出/校验结果）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                input_payload TEXT NOT NULL,
                output_text TEXT NOT NULL,
                compliance_result TEXT NOT NULL,
                is_degraded INTEGER DEFAULT 0,
                model TEXT
            )
        """)
        
        cursor.execute("SELECT COUNT(*) FROM sample_products")
        count = cursor.fetchone()[0]
        
        if count == 0:
            sample_products = [
                ('安心理财A', 70, 50000.0, '低风险', 4.2, '保本稳健型理财产品，适合保守投资者', 1),
                ('安心债券B', 70, 30000.0, '低风险', 3.8, '纯债基金，风险极低收益稳定', 1),
                ('稳健增值C', 70, 60000.0, '中低风险', 5.5, '固收增强型产品，稳健中追求收益', 0),
                ('成长先锋D', 71, 80000.0, '中风险', 8.5, '成长型股票基金，追求长期资本增值', 1),
                ('行业精选E', 71, 100000.0, '中高风险', 10.2, '行业轮动策略，精选高成长行业', 1),
                ('科技创新F', 71, 120000.0, '中高风险', 12.8, '专注科技创新领域的成长基金', 0),
                ('进取股票G', 72, 150000.0, '高风险', 15.5, '高收益股票型产品，适合风险承受能力强的投资者', 1),
                ('量化对冲H', 72, 180000.0, '高风险', 18.2, '量化对冲策略，追求绝对收益', 0),
                ('新兴产业I', 72, 200000.0, '高风险', 20.5, '投资新兴产业，高风险高回报', 1),
                ('杠杆增强J', 72, 250000.0, '极高风险', 25.0, '杠杆增强型产品，适合专业投资者', 0)
            ]
            
            cursor.executemany("""
                INSERT INTO sample_products 
                (name, category_id, price, risk_level, expected_return, description, is_popular)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, sample_products)
            
            print(f"已插入 {len(sample_products)} 个金融产品示例数据")
        
        add_sample_customer_data()
        
        conn.commit()
        _database_initialized = True
        print("数据库初始化完成")
        
    except Exception as e:
        print(f"数据库初始化错误: {e}")
        conn.rollback()
    finally:
        conn.close()

def add_sample_customer_data():
    """添加历史客户数据，创建丰富的购买记录用于关联分析"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) FROM customer_records")
        count = cursor.fetchone()[0]
        
        if count == 0:
            customer_purchases = [
                (1001, '张三', '安心理财A', 70, 50000.0),
                (1001, '张三', '安心债券B', 70, 30000.0),
                (1001, '张三', '稳健增值C', 70, 60000.0),
                (1001, '张三', '成长先锋D', 71, 80000.0),
                (1002, '李四', '成长先锋D', 71, 80000.0),
                (1002, '李四', '行业精选E', 71, 100000.0),
                (1002, '李四', '科技创新F', 71, 120000.0),
                (1002, '李四', '进取股票G', 72, 150000.0),
                (1002, '李四', '量化对冲H', 72, 180000.0),
                (1003, '王五', '安心理财A', 70, 50000.0),
                (1003, '王五', '成长先锋D', 71, 80000.0),
                (1003, '王五', '行业精选E', 71, 100000.0),
                (1003, '王五', '进取股票G', 72, 150000.0),
                (1003, '王五', '新兴产业I', 72, 200000.0),
                (1004, '赵六', '安心债券B', 70, 30000.0),
                (1004, '赵六', '安心理财A', 70, 50000.0),
                (1004, '赵六', '科技创新F', 71, 120000.0),
                (1004, '赵六', '杠杆增强J', 72, 250000.0),
                (1005, '钱七', '成长先锋D', 71, 80000.0),
                (1005, '钱七', '科技创新F', 71, 120000.0),
                (1005, '钱七', '行业精选E', 71, 100000.0),
                (1005, '钱七', '量化对冲H', 72, 180000.0),
                (1005, '钱七', '进取股票G', 72, 150000.0),
                (1005, '钱七', '新兴产业I', 72, 200000.0),
                (1006, '孙八', '安心理财A', 70, 50000.0),
                (1006, '孙八', '进取股票G', 72, 150000.0),
                (1006, '孙八', '稳健增值C', 70, 60000.0),
                (1007, '周九', '行业精选E', 71, 100000.0),
                (1007, '周九', '科技创新F', 71, 120000.0),
                (1007, '周九', '成长先锋D', 71, 80000.0),
                (1007, '周九', '进取股票G', 72, 150000.0),
                (1007, '周九', '安心理财A', 70, 50000.0),
                (1007, '周九', '量化对冲H', 72, 180000.0),
                (1008, '吴十', '安心理财A', 70, 50000.0),
                (1008, '吴十', '成长先锋D', 71, 80000.0),
                (1008, '吴十', '进取股票G', 72, 150000.0),
                (1008, '吴十', '量化对冲H', 72, 180000.0),
                (1008, '吴十', '行业精选E', 71, 100000.0),
            ]
            
            cursor.executemany("""
                INSERT INTO customer_records 
                (customer_id, customer_name, product_name, category_id, investment_amount)
                VALUES (?, ?, ?, ?, ?)
            """, customer_purchases)
            
            print(f"已插入 {len(customer_purchases)} 条历史客户购买记录")
            
            # 客户记录表（customer_inputs）保持为空，用于前端输入
        
        conn.commit()
        
    except Exception as e:
        print(f"添加历史客户数据错误: {e}")
        conn.rollback()
    finally:
        conn.close()

def get_financial_products():
    """获取所有金融产品数据"""
    init_database()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, name, category_id, price, risk_level, expected_return, description, is_popular
            FROM sample_products
        """)
        results = cursor.fetchall()
        
        products = []
        for row in results:
            products.append({
                'id': row[0],
                'name': row[1],
                'category_id': row[2],
                'price': row[3],
                'risk_level': row[4],
                'expected_return': row[5],
                'description': row[6],
                'is_popular': bool(row[7])
            })
        
        return products
    finally:
        conn.close()

def get_categories():
    """获取金融产品分类"""
    categories = [
        {'id': 70, 'name': '稳健理财'},
        {'id': 71, 'name': '成长基金'},
        {'id': 72, 'name': '进取投资'}
    ]
    return categories

def add_customer_input(preferred_category, investment_amount, min_distance, is_abnormal=0):
    """添加前端输入的客户记录（包含最小距离）"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO customer_inputs 
            (preferred_category, investment_amount, min_distance, is_abnormal)
            VALUES (?, ?, ?, ?)
        """, (preferred_category, investment_amount, min_distance, is_abnormal))
        conn.commit()
        return True
    except Exception as e:
        print(f"添加客户输入错误: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_customer_inputs(limit=100):
    """获取前端输入的客户记录"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, preferred_category, investment_amount, min_distance, is_abnormal, created_time
            FROM customer_inputs 
            ORDER BY created_time DESC 
            LIMIT ?
        """, (limit,))
        results = cursor.fetchall()
        
        inputs = []
        for row in results:
            inputs.append({
                'id': row[0],
                'preferred_category': row[1],
                'investment_amount': row[2],
                'min_distance': row[3],
                'is_abnormal': bool(row[4]),
                'created_time': row[5]
            })
        
        return inputs
    finally:
        conn.close()

def get_customer_records():
    """获取历史客户购买记录（用于关联分析）"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT customer_id, customer_name, product_name, category_id, investment_amount, created_time
            FROM customer_records 
            ORDER BY customer_id, created_time
        """)
        results = cursor.fetchall()
        
        records = []
        for row in results:
            records.append({
                'customer_id': row[0],
                'customer_name': row[1],
                'product_name': row[2],
                'category_id': row[3],
                'investment_amount': row[4],
                'created_time': row[5]
            })
        
        return records
    finally:
        conn.close()

def get_popular_products():
    """获取热门产品"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, name, category_id, price, risk_level, expected_return, description
            FROM sample_products 
            WHERE is_popular = 1
            ORDER BY expected_return DESC
        """)
        results = cursor.fetchall()
        
        products = []
        for row in results:
            products.append({
                'id': row[0],
                'name': row[1],
                'category_id': row[2],
                'price': row[3],
                'risk_level': row[4],
                'expected_return': row[5],
                'description': row[6]
            })
        
        return products
    finally:
        conn.close()

def get_products_by_category(category_id):
    """根据分类获取产品"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, name, category_id, price, risk_level, expected_return, description
            FROM sample_products 
            WHERE category_id = ?
        """, (category_id,))
        results = cursor.fetchall()
        
        products = []
        for row in results:
            products.append({
                'id': row[0],
                'name': row[1],
                'category_id': row[2],
                'price': row[3],
                'risk_level': row[4],
                'expected_return': row[5],
                'description': row[6]
            })
        
        return products
    finally:
        conn.close()

def add_audit_log(input_payload, output_text, compliance_result, is_degraded=0, model=None):
    """写入一条 Agent 审计日志（DAT-01：输入/输出/校验结果，调用时间自动生成）"""
    init_database()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO agent_audit_log
            (input_payload, output_text, compliance_result, is_degraded, model)
            VALUES (?, ?, ?, ?, ?)
        """, (input_payload, output_text, compliance_result, int(is_degraded), model))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"写入审计日志错误: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

def get_audit_logs(limit=50):
    """读取最近的 Agent 审计日志（验收检查/演示用）"""
    init_database()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, call_time, input_payload, output_text, compliance_result, is_degraded, model
            FROM agent_audit_log
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        results = cursor.fetchall()

        logs = []
        for row in results:
            logs.append({
                'id': row[0],
                'call_time': row[1],
                'input_payload': row[2],
                'output_text': row[3],
                'compliance_result': row[4],
                'is_degraded': bool(row[5]),
                'model': row[6]
            })
        return logs
    finally:
        conn.close()


# 只有在直接运行此文件时才初始化数据库
if __name__ == "__main__":
    init_database()
else:
    # 如果是被导入的，延迟初始化到第一次使用时
    pass