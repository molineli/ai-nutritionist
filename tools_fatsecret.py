import requests
import json
import os
from typing import Type
from concurrent.futures import ThreadPoolExecutor
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


# ============================================================
# 1. 输入参数定义
# ============================================================
class FatSecretInput(BaseModel):
    query: str = Field(...,
                       description="A comma-separated list of foods to search. E.g., 'rice, chicken breast, broccoli'.")


# ============================================================
# 2. 核心工具类
# ============================================================
class FatSecretSearchTool(BaseTool):
    name: str = "Search FatSecret Nutrition Data"
    description: str = (
        "Useful for searching nutritional info for multiple foods at once. "
        "Returns calories/macros per 100g. "
        "You MUST provide the argument 'query' with a comma-separated string."
    )
    args_schema: Type[BaseModel] = FatSecretInput

    # API 凭证 (由 app.py 传入)
    client_id: str = Field(..., description="FatSecret Client ID")
    client_secret: str = Field(..., description="FatSecret Client Secret")

    # 内部状态
    token: str = Field(default=None, exclude=True)
    cache_file: str = "food_cache_db.json"

    token_url: str = "https://oauth.fatsecret.com/connect/token"
    api_url: str = "https://platform.fatsecret.com/rest/server.api"

    def _get_access_token(self):
        """获取 OAuth 2.0 Token"""
        if self.token: return self.token
        try:
            # 如果是 mock ID，直接返回 None，不进行真实请求
            if self.client_id == "mock_id":
                return None

            res = requests.post(
                self.token_url,
                data={"grant_type": "client_credentials", "scope": "basic"},
                auth=(self.client_id, self.client_secret),
                timeout=10
            )
            res.raise_for_status()
            self.token = res.json()["access_token"]
            return self.token
        except Exception as e:
            # 这里的 print 会显示在后台终端，方便调试
            print(f"Auth Error: {e}")
            return None

    # ============================================================
    # 缓存管理
    # ============================================================
    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_cache(self, key, value):
        try:
            current_cache = self._load_cache()
            current_cache[key] = value
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(current_cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ============================================================
    # 单个食物查询逻辑
    # ============================================================
    def _search_single_food(self, query: str) -> str:
        clean_query = query.strip().lower()
        if not clean_query: return ""

        # 1. 查缓存
        cache = self._load_cache()
        if clean_query in cache:
            return f"[Cache] {cache[clean_query]}"

        # 2. 联网查
        token = self._get_access_token()
        # 如果没有 Token (比如用户没填Key)，返回模拟数据防止程序崩溃
        if not token:
            return f"[{clean_query}]: Auth Failed (Using Mock Data: 100kcal/100g)"

        headers = {"Authorization": f"Bearer {token}"}

        try:
            # 步骤A: 搜索 ID
            search_res = requests.get(
                self.api_url,
                headers=headers,
                params={"method": "foods.search", "search_expression": clean_query, "format": "json", "max_results": 1},
                timeout=10
            ).json()

            foods = search_res.get("foods", {}).get("food", [])
            if not foods: return f"[{clean_query}]: Not Found in Database"

            food_id = foods[0]["food_id"] if isinstance(foods, list) else foods["food_id"]

            # 步骤B: 获取详情
            detail_res = requests.get(
                self.api_url,
                headers=headers,
                params={"method": "food.get.v2", "food_id": food_id, "format": "json"},
                timeout=10
            ).json()

            food_data = detail_res.get("food", {})
            food_name = food_data.get("food_name", clean_query)

            # 步骤C: 寻找 100g 数据
            servings = food_data.get("servings", {}).get("serving", [])
            if isinstance(servings, dict): servings = [servings]

            target = servings[0] if servings else {}
            for s in servings:
                if s.get("metric_serving_unit") == "g" and "100" in s.get("metric_serving_amount", ""):
                    target = s
                    break

            # 格式化输出
            output = (
                f"{food_name} | "
                f"Kcal: {target.get('calories', 0)} | "
                f"P: {target.get('protein', 0)}g | "
                f"C: {target.get('carbohydrate', 0)}g | "
                f"F: {target.get('fat', 0)}g (per 100g)"
            )

            # 3. 写入缓存
            self._save_cache(clean_query, output)
            return output

        except Exception as e:
            return f"[{clean_query}]: API Error {str(e)}"

    # ============================================================
    # 执行入口 (并发处理)
    # ============================================================
    def _run(self, query: str) -> str:
        """支持一次性查询多个，逗号分隔"""
        # 防止 None 输入
        if not query:
            return "Please provide valid food names."

        food_list = [f.strip() for f in query.split(',') if f.strip()]

        if not food_list:
            return "Please provide food names."

        results = []
        # 使用5个线程并发查询
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(self._search_single_food, food_list))

        return "\n".join(results)