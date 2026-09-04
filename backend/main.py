from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import database.db_connection as db
from services import recommendation_service

app = FastAPI()

# CORS 配置：放行 Streamlit 前端默认端口 8501（见需求文档 5.5 / 落地清单 UI-02）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",
        "http://127.0.0.1:8501",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "金融产品推荐系统"}

@app.get("/api/products/")
def get_products(category_id: int = None):
    """获取金融产品列表"""
    products = db.get_financial_products()
    
    if category_id:
        products = [p for p in products if p['category_id'] == category_id]
    
    return {"products": products}

@app.get("/api/products/all/")
def get_all_products():
    """获取所有金融产品（用于关联规则选择）"""
    products = db.get_financial_products()
    return {"products": products}

@app.get("/api/categories/")
def get_categories():
    """获取金融产品分类列表"""
    categories = db.get_categories()
    return {"categories": categories}

@app.post("/api/recommend/")
def get_recommendations(data: dict):
    """获取推荐结果（支持最近邻和关联规则两种算法，编排层 SVC-01）"""
    return recommendation_service.run_recommendation(data)

@app.post("/api/recommend/explain")
def explain_recommendations(data: dict):
    """AI 合规解读（SVC-02）：推荐结果 + 用户上下文 → 合规解读文本（含降级模板路径）"""
    recommendations = data.get('recommendations')

    if not recommendations:
        return {"error": "缺少推荐结果"}

    user_context = data.get('user_context') or {}
    return recommendation_service.generate_explanation(recommendations, user_context)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)