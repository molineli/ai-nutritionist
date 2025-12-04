import os
from crewai import Agent, Task, Crew, Process, LLM
# 关键导入
from langchain_openai import ChatOpenAI

os.environ["OPENAI_API_KEY"] = "sk-09991f3a85344338be57d0c6876fd5d7"

# 2. 强制将所有 OpenAI 请求重定向到阿里云 (这就是之前报错的原因，因为没定向成功)
os.environ["OPENAI_API_BASE"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
os.environ["OPENAI_BASE_URL"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 3. 设置默认模型名称
os.environ["OPENAI_MODEL_NAME"] = "qwen3-max"

# 4. 禁用 CrewAI 的遥测和不必要的联网检查
os.environ["CREWAI_TELEMETRY_OPT_OUT"] = "true"


# 1. 配置 Qwen 模型
qwen_llm = ChatOpenAI(
    model="qwen3-max",
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ["OPENAI_API_BASE"],
    temperature=0.7
)

# 2. 将 LLM 赋予 Agent
researcher = Agent(
    role='高级研究员',
    goal='发现 AI 技术的最前沿进展',
    backstory='你是一名顶尖的科技研究员，擅长从繁杂的信息中提炼关键点。',
    llm=qwen_llm,  # <--- 关键点：指定使用 Qwen
    verbose=True,
    allow_delegation=False
)

writer = Agent(
    role='科技博主',
    goal='根据研究员的发现写一篇引人入胜的博客文章',
    backstory='你是一名资深科技博主，擅长把复杂的技术概念用通俗易懂的语言讲给大众听。',
    llm=qwen_llm,  # <--- 每个 Agent 都可以指定不同的模型（比如 researcher 用 max，writer 用 turbo）
    verbose=True,
    allow_delegation=False
)

# 后面的 Task 和 Crew 定义与之前一样...
# 2. 定义 Task (任务)
task1 = Task(
    description='研究2024年关于 LLM (大语言模型) Agent 的最新趋势。',
    agent=researcher,
    expected_output='一份包含3个关键趋势的简报'
)

task2 = Task(
    description='根据研究员的简报，写一篇关于 AI Agent 未来的 300字 博客文章。',
    agent=writer,
    expected_output='一篇格式精美的博客文章'
)

# 3. 组建 Crew (团队)
crew = Crew(
    agents=[researcher, writer],
    tasks=[task1, task2],
    verbose=True,  # 打印详细日志
    process=Process.sequential,  # 顺序执行：先研究，后写作
    memory=False,
    tracing=True
)

# 4. 开始执行
result = crew.kickoff()

print("######################")
print(result)
