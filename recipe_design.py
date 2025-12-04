import os
from crewai import Agent, Task, Crew, Process
from tools_fatsecret import FatSecretSearchTool
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

os.environ["CREWAI_TELEMETRY_OPT_OUT"] = "true"

# 1. 配置 Qwen 模型
qwen_llm = ChatOpenAI(
    model="qwen3-max",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_API_BASE"),
    temperature=0.7
)

fatsecret_tool_instance = FatSecretSearchTool(
    client_id=os.getenv('FATSECRET_CLIENT_ID'),
    client_secret=os.getenv('FATSECRET_CLIENT_SECRET')
)


def create_nutrition_crew():
    # ==============================================================================
    # 1. 定义 Agents (智能体)
    # ==============================================================================

    # Agent-1: 用户画像分析师
    profile_analyst = Agent(
        role='资深用户画像分析师',
        goal='建立带有医学视角的营养诊断书',
        backstory="""你是一名专业的健康数据分析师。
        你擅长从用户零散的描述中挖掘出关键信息，进行风险分层、生活流标签化以及明确核心目标""",
        llm=qwen_llm,
        verbose=True,
        allow_delegation=False,
        memory=True  # 开启短期记忆
    )

    # Agent-2: 营养科学计算器
    clinical_calculator = Agent(
        role='临床营养学家',
        goal='基于用户画像，计算精确的 TDEE（每日总能量消耗）、BMI，并制定宏量营养素分配方案。',
        backstory="""你是一名严谨的临床营养师。你只相信数据和生化指标。
        你需要根据用户的目标进行合理安排和计算。
        你需要根据用户的疾病情况（如糖尿病、高血压）给出具体的营养限制策略（如：限钠、控糖）。
        你需要输出具体的数字：总热量、碳水/蛋白/脂肪的克数。""",
        llm=qwen_llm,
        verbose=True,
        allow_delegation=False
    )

    # 3. Agent-3: 膳食架构师
    menu_architect = Agent(
        role='高级膳食策划师',
        goal='将枯燥的营养数据转化为美味、可执行的一日三餐食谱。',
        backstory="""你是一名精通'食物交换份法'的营养师。
        你拥有查询权威数据库(FatSecret)的能力。
        你必须根据计算出的份数，安排具体的食材和重量。
        例如：如果你查询到米饭100g是130kcal，而你需要安排2份谷薯(180kcal)，
        你应该计算出需要 180/130*100 = 约138g 米饭。""",

        # === 这里挂载 FatSecret 工具 ===
        tools=[fatsecret_tool_instance],

        verbose=True,
        allow_delegation=False
    )

    # Agent-4: 质检与仿真专员
    qa_simulator = Agent(
        role='食谱质检员与用户模拟器',
        goal='模拟用户视角体验食谱，并检查营养指标的合规性。',
        backstory="""你非常挑剔。你会扮演用户去'试吃'这份食谱。
        如果食谱太难做、食材太贵、口感太单一、与用户的目标不符或违反医嘱，你必须提出批评并修正。
        你需要确保最终输出包含购物清单和备餐指南。""",
        llm=qwen_llm,
        verbose=True,
        allow_delegation=True  # 允许它指派任务回给架构师进行修改（在复杂流程中有效，这里简化为单向）
    )

    # ==============================================================================
    # 2. 定义 Tasks (任务)
    # ==============================================================================

    task_profile = Task(
        description="""
        **任务目标**：对用户提供的自然语言描述进行深度拆解。

        **输入数据**：
        {user_input_context}

        **执行步骤**：
        1. **数据清洗**：提取基础生理数据。
        2. **风险评估**：结合BMI和体检异常，判断代谢风险等级。
        3. **生活流标签化**：根据职业和习惯打标签（如 "时间匮乏型", "高钠风险"）。
        4. **隐性需求挖掘**：找出心理弱点。
        5. **总结核心目标**： 根据用户目标进行总结

        **输出要求**：
        输出一份严格的 JSON 格式报告。
        """,
        expected_output="包含风险评估和生活方式标签的深度用户画像 JSON。",
        agent=profile_analyst
    )

    task_calculation = Task(
        description="""
        **任务目标**：制定精准的医学营养干预方案（MNT）。

        **执行步骤**：
        1. **能量计算**：计算 BMR 和 TDEE，设定热量缺口/盈余。
        2. **宏量营养素分配**：确定 碳水/蛋白质/脂肪 的供能比。
        3. **食物交换份转化（核心）**：
           - 将总热量拆解为：谷薯类、肉蛋类、蔬果类、油脂类的具体“份数”。
           - 标准：1份 = 90kcal。
           - 输出每日所需的各类别总份数（例如：谷薯 8份, 肉蛋 5份...）。
        4. **针对特殊情况给出具体的饮食红线（如：禁酒、低GI）。
        """,
        expected_output="一份包含详细的营养处方，热量、宏量元素克数,食物交换份总数和医学营养治疗原则的计算报告。",
        agent=clinical_calculator,
        context=[task_profile]
    )

    task_menu_design = Task(
        description="""
        **任务目标**：将抽象的营养数字落地为用户场景下可执行的食谱。

        **核心约束**：
        - 必须严格遵循用户偏好和禁忌。
        - **场景适配**：如果用户中午吃外卖，请推荐具体的外卖选购组合。
        - 满足用户目标。
        
        ** 创新菜品指令 (反枯燥机制)**：
        - **今日限定主题**：请严格围绕 **"{creative_theme}"** 风格来设计菜品口味和烹饪方式。
        - **拒绝刻板印象**：
           - 除非用户患有严重胃病，否则**严禁**推荐"无味水煮鸡胸肉"、"白灼西兰花"等枯燥菜式。
           - 请灵活运用低卡调味（如：柠檬汁、黑胡椒、辣椒粉、醋、蒜泥、香草）来丰富口感。
           - 如果是减脂餐，请设计得像"欺骗餐"一样美味，但热量达标。


        **工具使用策略（强制执行）**：
        1. **Step 1 - 拟定**：先在脑海中构思一日三餐的食材。
        2. **Step 2 - 批量查询**：将所有拟定的食材整理成一个逗号分隔的列表（例如："rice, milk..."）。
        3. **Step 3 - 单次调用**：调用 Search Tool **一次性**获取数据。
                   - **⚠️ 重要参数说明**: 工具接受的参数名为 `query`。
                   - **正确调用示例**: `Search FatSecret Nutrition Data(query="rice, egg")`
                   - **错误调用示例**: `Search FatSecret Nutrition Data("rice, egg")` 或使用中文
                                     `Search FatSecret Nutrition Data("米饭， 鸡蛋")`
        4. **Step 4 - 份额计算**：`食材重量(g) = (计划摄入热量 / 该食材每100g热量) * 100`。

        **格式要求**：
        请输出标准的 Markdown 表格，列出：[餐次, 推荐菜品, 核心食材及生重(g), 热量估算]。
        """,
        expected_output="一份包含详细食材重量、热量标注及外卖指南的Markdown格式食谱。",
        agent=menu_architect,
        context=[task_profile, task_calculation]
    )

    task_qa_review = Task(
        description="""
        **任务目标**：对食谱进行“压力测试”。

        **检查项**：
        1. **风格一致性**：检查食谱是否符合 **"{creative_theme}"** 的主题？如果是“川渝风味”却全是水煮菜，请驳回重写。
        2. **时间可行性**：用户的工作强度能否完成此烹饪？
        3. **医疗安全**：是否违反了用户的病史禁忌？
        4. **数据核对**：抽查热量计算是否准确。
        5. **目标完成度** 检查是否满足用户的目标

        **最终交付**：
        生成最终文档，包括：
        - [最终食谱表格]
        - [分类购物清单]
        - [暖心备餐指南]
        """,
        expected_output="最终确认的食谱文档，语言亲切，包含鼓励话语。",
        agent=qa_simulator,
        context=[task_menu_design, task_calculation]
    )

    # ==============================================================================
    # 3. 组建 Crew 并执行
    # ==============================================================================

    nutrition_crew = Crew(
        agents=[profile_analyst, clinical_calculator, menu_architect, qa_simulator],
        tasks=[task_profile, task_calculation, task_menu_design, task_qa_review],
        process=Process.sequential,  # 顺序执行：Task 1 -> Task 2 -> Task 3 -> Task 4
        verbose=True,
        tracing=True
    )

    return nutrition_crew
