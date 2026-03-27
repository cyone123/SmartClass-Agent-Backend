from typing import Literal
from pydantic import BaseModel, Field
from langchain.messages import HumanMessage, SystemMessage
from langgraph.types import Command, interrupt
from app.core.state import TeachingAssistantState, TeachingMetadata
from app.core.agent import get_model
from app.core.state import TeachingAssistantState

llm = get_model()

class IntentRoute(BaseModel):
    intent: Literal["normal_chat", "teaching_plan"] = Field(None, description="User's intention")

router = llm.with_structured_output(IntentRoute)

# 意图识别路由节点
def intent_router_node(state: TeachingAssistantState):
    decision = router.invoke(
        [
            SystemMessage(
                content="分析用户输入的内容的意图，如果是日常对话路由到normal_chat。如果让你帮助备课，路由到teaching_plan"
            ),
            state["message"][-1],
        ]
    )
    return {"intent": decision.intent}


def route_decision(state: TeachingAssistantState):
    if state["intent"] == "normal_chat":
        return "normal_chat_node"
    elif state["intent"] == "teaching_plan":
        return "metadata_structer_node"
    else:
        return "Error"

# 普通日常聊天节点
def normal_chat_node(state: TeachingAssistantState):
    response = llm.ainvoke([*state["messages"]])
    return {"messages": [response]}

# 结构化元数据节点
def metadata_structer_node(state: TeachingAssistantState):
    system_prompt = "你需要联系上下文把用户提到的教学要素提取出来并结构化输出,用户没有提到的要素为None。当所有要素都有时is_complete为true，否则为false"
    structed_llm = llm.with_structed_outpue(TeachingMetadata)
    response = structed_llm.ainvoke([SystemMessage(content=system_prompt), *state["messages"]])
    return {"teaching_metadata": response}

# 元数据完整性验证条件边
def metadata_completion_condition(state: TeachingAssistantState):
    if state["teaching_metadata"]["is_complete"]:
        return "reg_retrieval_node"
    else:
        return "follow_up_questioner"

# 主动追问节点，下一节点为结构化元数据节点
def follow_up_questioner(state: TeachingAssistantState):
    system_prompt = f"你需要联系上下文和提供的教学要素，主动追问用户补充教学要素，目前的教学要素是：{state["teaching_metadata"]},其中为None的是缺失的。"
    # 不携带历史消息上下文
    response = llm.ainvoke([SystemMessage(content=system_prompt)])
    return {"messages": [response]}

# 中断等待用户输入节点
def interrupt_for_userinput(state: TeachingAssistantState):
    user_input = interrupt({"question": state["messages"][-1].content})
    return {"messages": user_input}

# RAG检索节点
def rag_retrieval_node(state: TeachingAssistantState):
    pass

# 教学设计总体计划节点
def teaching_design_planner(state: TeachingAssistantState):
    system_prompt = f"根据用户提供的信息、教学元数据以及检索到的相关资料，进行教学计划的总体设计。教学元数据：{state["teaching_metadata"]}。RAG检索到的资料：{state["rag_results"]}"
    response = llm.ainvoke(SystemMessage(content=system_prompt))
    return {"teaching_design_plan": [response]}



