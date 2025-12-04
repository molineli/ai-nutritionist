# app.py
import streamlit as st
import sys
import threading
import queue
import re
import time
from recipe_design import create_nutrition_crew
import random

# 设置页面配置
st.set_page_config(
    page_title="AI 深度定制营养师",
    page_icon="🥗",
    layout="wide"
)


# =========================================================
# 核心组件：日志重定向器
# 用于捕获 CrewAI 的打印输出并显示在 Streamlit 界面上
# =========================================================
class QueueLogger:
    """
    一个线程安全的日志捕获器。
    它替代 sys.stdout，将所有 print 内容放入队列，而不是直接操作 UI。
    """

    def __init__(self, log_queue):
        self.log_queue = log_queue
        self.terminal = sys.stdout  # 保留原终端输出
        self.ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def write(self, message):
        # 1. 输出到控制台（方便调试）
        self.terminal.write(message)

        # 2. 放入队列（给UI显示）
        if message.strip():
            clean_text = self.ansi_escape.sub('', message)
            self.log_queue.put(clean_text)

    def flush(self):
        self.terminal.flush()


# =========================================================
# 定义风味主题库 (扩充版)
# =========================================================
ALL_THEMES = [
    # --- 西式/异域 ---
    "地中海风味 (橄榄油/番茄/海鲜/原味)",
    "东南亚清新 (柠檬草/酸辣/鱼露/椰浆)",
    "日式极简 (味噌/烤物/昆布高汤)",
    "法式轻食 (慢煮/香草/红酒醋汁)",

    # --- 中式地域风味 ---
    "粤式清淡 (清蒸/煲汤/白灼/讲究鲜味)",
    "川渝麻辣 (花椒/辣椒/红油/开胃)",
    "湘菜香辣 (鲜椒/小炒/入味下饭)",
    "淮扬鲜甜 (炖煮/刀工/清鲜平和)",
    "东北炖菜 (酱香/乱炖/量大豪爽)",
    "西北风味 (面食/牛羊肉/孜然)",
    "云南山野 (菌菇/酸木瓜/香料丰富)",

    # --- 功能/创意类 ---
    "多彩彩虹碗 (强调食材颜色的丰富度)",
    "温暖治愈系 (砂锅/炖菜/软糯易消化)",
    "低卡欺骗餐 (重口味但低热量的创意菜)"
]

# =========================================================
# GUI 布局
# =========================================================

st.title("🥗 AI 深度定制营养师")
st.markdown("基于 Multi-Agent 架构与 FatSecret 真实数据驱动")

# --- 左侧侧边栏：用户输入 ---
with st.sidebar:
    st.header("📝 用户档案录入")

    col_a, col_b = st.columns(2)
    with col_a:
        gender = st.selectbox("性别", ["男", "女"])
        height = st.number_input("身高 (cm)", min_value=30, max_value=250)
    with col_b:
        age = st.number_input("年龄", min_value=1, max_value=120)
        weight = st.number_input("体重 (kg)", min_value=5.0, max_value=300.0)

    job_desc = st.text_input("职业与工作强度", "程序员，996久坐，压力大")

    st.subheader("饮食习惯")
    breakfast = st.text_input("早餐场景", "没时间吃，或者便利店")
    lunch = st.text_input("午餐场景", "点外卖，油腻")
    dinner = st.text_input("晚餐场景", "家里简单煮，或者不吃")

    health_issues = st.text_input("体检异常/病史", "轻度脂肪肝，尿酸临界值")
    preferences = st.text_area("偏好与禁忌", "不吃香菜，不吃内脏，喜欢吃辣，想减脂")
    goals = st.text_area("目标", "减轻体重，改善免疫力，均衡营养等")

    st.divider()

    # --- 风味选择逻辑 (新增) ---
    st.subheader("🎨 食谱风格定制")
    # 选项列表：第一个是随机，后面是具体风味
    style_options = ["🎲 帮我随机选 (Surprise Me!)"] + ALL_THEMES
    selected_style_option = st.selectbox(
        "选择您本周想尝试的口味：",
        style_options,
        index=0  # 默认选第一个
    )

    btn_generate = st.button("🚀 生成专属食谱", type="primary", use_container_width=True)

# --- 右侧主区域：展示 ---
col_log, col_result = st.columns([1, 1.2])

with col_log:
    st.subheader("🤖 AI 思考全流程")
    # 创建一个固定高度的滚动容器
    log_container = st.container(height=1000)
    log_text_element = log_container.empty()

with col_result:
    st.subheader("📋 最终交付方案")
    result_container = st.empty()
    result_container.info("食谱生成后将在此显示...")

# =========================================================
# 执行逻辑
# =========================================================
if btn_generate:
    # --- 确定最终风味主题 ---
    if selected_style_option.startswith("🎲"):
        # 如果用户选了随机，我们就从列表中抽一个
        daily_theme = random.choice(ALL_THEMES)
        is_random = True
    else:
        # 如果用户指定了，就用用户指定的
        daily_theme = selected_style_option
        is_random = False

    # 构建全景 Context (Prompt Engineering)
    user_context = f"""
    【用户全景档案】
    - 基础数据: 性别{gender}, {age}岁, {height}cm, {weight}kg
    - 职业生活: {job_desc}
    - 饮食场景: 早餐[{breakfast}], 午餐[{lunch}], 晚餐[{dinner}]
    - 医学状况: {health_issues}
    - 偏好禁忌: {preferences}
    - 目标: {goals}
    """

    inputs = {
        "user_input_context": user_context,
        "creative_theme": daily_theme
    }

    # 在界面上展示选定的主题，增加交互感
    if is_random:
        st.info(f"✨ 既然您选择了随机，AI 为您挑选了灵感主题：**{daily_theme}**")
    else:
        st.success(f"👌 没问题，将为您定制 **{daily_theme}** 风格的食谱")

    # 初始化环境
    log_queue = queue.Queue()
    # 临时替换标准输出，捕获所有 Agent 的 print
    original_stdout = sys.stdout
    sys.stdout = QueueLogger(log_queue)

    full_logs = ""
    result_holder = {"data": None, "error": None}

    # 定义后台任务函数
    def run_crew_task():
        try:
            crew = create_nutrition_crew()
            result_holder["data"] = crew.kickoff(inputs=inputs)
        except Exception as e:
            result_holder["error"] = str(e)


    # 启动后台线程运行 AI
    # 注意：我们不在主线程跑 kickoff，因为它会阻塞 UI 刷新
    thread = threading.Thread(target=run_crew_task)
    thread.start()

    # 主线程循环：监听队列并更新 UI
    # 只要线程还在跑，我们就不断刷新日志
    with st.spinner("AI 专家团队正在协作中..."):
        while thread.is_alive():
            # 消费队列中的所有新日志
            while not log_queue.empty():
                new_line = log_queue.get()
                full_logs += new_line + "\n"
                # 更新 UI (这步在主线程，所以是安全的)
                log_text_element.code(full_logs, language='text', line_numbers=False)

            # 稍微休息一下，避免 CPU 占用过高
            time.sleep(0.1)

        # 线程结束后，再检查一次队列，确保没有遗漏
        while not log_queue.empty():
            new_line = log_queue.get()
            full_logs += new_line + "\n"
            log_text_element.code(full_logs, language='text', line_numbers=False)

    # 恢复标准输出 & 显示结果
    sys.stdout = original_stdout
    thread.join()

    if result_holder["error"]:
        st.error(f"运行出错: {result_holder['error']}")
    elif result_holder["data"]:
        result_container.markdown(result_holder["data"])
        st.success("✅ 生成完成！")
        # 提供下载按钮
        st.download_button(
            label="📥 下载食谱 (Markdown)",
            data=str(result_holder["data"]),
            file_name="my_diet_plan.md",
            mime="text/markdown"
        )
        st.balloons()
