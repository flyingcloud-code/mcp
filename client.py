import asyncio # 导入 asyncio 库，用于异步 I/O 操作
import json # 导入 json 库，用于处理 JSON 数据
import os # 导入 os 库，用于与操作系统交互，例如读取环境变量
import anyio # Import anyio for exception handling

from typing import Optional # 从 typing 模块导入 Optional 类型提示，表示变量可以是指定类型或 None
from contextlib import AsyncExitStack # 从 contextlib 模块导入 AsyncExitStack，用于管理异步上下文管理器

from mcp import ClientSession, StdioServerParameters # 从 mcp 库导入 ClientSession 和 StdioServerParameters 类
from mcp.client.stdio import stdio_client # 从 mcp.client.stdio 模块导入 stdio_client 函数

from dotenv import load_dotenv # 从 dotenv 库导入 load_dotenv 函数，用于从 .env 文件加载环境变量
from openai import OpenAI # 从 openai 库导入 OpenAI 类，用于与 OpenAI API 交互

load_dotenv() # 加载当前目录或父目录中的 .env 文件中的环境变量


llm_client = OpenAI( # 创建一个 OpenAI 客户端实例
    base_url=os.getenv("API_URL"), # 设置 API 的基础 URL，从环境变量 "API_URL" 获取
    api_key=os.getenv("OPENAI_API_KEY"), # 设置 API 密钥，从环境变量 "OPENAI_API_KEY" 获取
)


class MCPClient: # 定义一个名为 MCPClient 的类
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        # Initialize message history with the system prompt
        self.messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant equipped with several tools. \n\n**Workflow Guidance:**\n1. Analyze the user's request. \n2. If the request requires current information or details from the web, first use `google_search` to find relevant URLs.\n3. If the search results provide promising URLs, consider using `get_web_content` on the most relevant URL to fetch its detailed content.\n4. Synthesize the information from the search results and/or the fetched web content to answer the user's question.\n5. For other requests, use the appropriate tool directly or answer based on your knowledge."
            }
        ]

    async def process_query(self, query: str) -> str:
        # Append the new user query to the history
        self.messages.append({
            "role": "user",
            "content": query
        })

        response = await self.session.list_tools()
        available_tools = [{
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": {
                    "type": tool.inputSchema["type"],
                    "required": tool.inputSchema["required"],
                    "properties": tool.inputSchema["properties"],
                }
            }
        } for tool in response.tools]
        #print(json.dumps(available_tools, indent=4))

        # Initial Claude API call # 对 LLM (如 Claude 或 OpenAI 模型) 进行初始 API 调用
        first_response = llm_client.chat.completions.create(
            model=os.getenv("MODEL_NAME"),
            messages=self.messages,
            tools=available_tools,
            tool_choice="auto",
            max_tokens=4096,
            temperature=0,
        )

        # Extract the first message choice
        first_message = first_response.choices[0].message

        # Append the assistant's response (or tool calls) to the history
        self.messages.append({
            "role": "assistant",
            "content": first_message.content,
            "tool_calls": first_message.tool_calls,
        })

        stop_reason = (
            "tool_calls"
            if first_message.tool_calls is not None
            else first_response.choices[0].finish_reason
        )

        tool_results_for_next_call = [] # Store tool results for the next LLM call
        if stop_reason == "tool_calls":
            for tool_call in first_message.tool_calls:
                arguments = (
                    json.loads(tool_call.function.arguments)
                    if isinstance(tool_call.function.arguments, str)
                    else tool_call.function.arguments
                )
                print(f"Using tool: {tool_call.function.name}")
                tool_result = await self.session.call_tool(tool_call.function.name, arguments=arguments)

                # Prepare tool result message for history and next call
                tool_result_message = {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": tool_result.content[0].text,
                }
                self.messages.append(tool_result_message) # Add tool result to history
                tool_results_for_next_call.append(tool_result_message) # Keep track for potential next call

            # Query LLM again with the tool results included in the history
            print("\n[DEBUG] Messages before second LLM call:")
            # Create a JSON-serializable copy of messages before dumping
            serializable_messages = []
            for msg in self.messages:
                serializable_msg = msg.copy()
                # Handle tool_calls if present
                if 'tool_calls' in serializable_msg and serializable_msg['tool_calls'] is not None:
                    # Convert tool_calls to a serializable format
                    tool_calls_serializable = []
                    for tc in serializable_msg['tool_calls']:
                        tool_calls_serializable.append({
                            'id': tc.id,
                            'type': tc.type,
                            'function': {
                                'name': tc.function.name,
                                'arguments': tc.function.arguments
                            }
                        })
                    serializable_msg['tool_calls'] = tool_calls_serializable
                serializable_messages.append(serializable_msg)
            try:
                print(json.dumps(serializable_messages, indent=2))
            except Exception as e:
                print(f"Could not serialize messages: {e}")
            
            # Ensure messages are properly serialized for the LLM call
            llm_messages = serializable_messages
            
            # If we already have tool results, prevent further tool calls
            if tool_results_for_next_call:
                new_response = llm_client.chat.completions.create(
                    model=os.getenv("MODEL_NAME"),
                    messages=llm_messages,
                    tools=[], # Disable tools for subsequent calls
                    max_tokens=4096,
                    temperature=0,
                )
            else:
                new_response = llm_client.chat.completions.create(
                    model=os.getenv("MODEL_NAME"),
                    messages=llm_messages,
                    tools=available_tools,
                    tool_choice="auto",
                    max_tokens=4096,
                    temperature=0,
                )
            print("\n[DEBUG] Response from second LLM call:")
            print(new_response)
            final_message_content = new_response.choices[0].message.content
            #print(f"\n[DEBUG] Final message content extracted: {final_message_content}")
            # Append the final assistant response to history
            self.messages.append({"role": "assistant", "content": final_message_content})

        elif stop_reason == "stop":
            # If the LLM stopped on its own, the content is already in history
            final_message_content = first_message.content
            # No need to call LLM again or append assistant message, it's already there

        else:
            raise ValueError(f"Unknown stop reason: {stop_reason}")

        # Return the final assistant response content
        #print(f"\n[DEBUG] Returning final message content: {final_message_content}")
        return final_message_content


    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")

        while True:
            try:
                query = input("\nQuery: ").strip()

                if query.lower() == 'quit':
                    break

                if not self.session: # Check if session exists before processing
                    print("\nError: Not connected to server. Attempting to reconnect...")
                    await self.connect_to_server("./server.py")
                    print("Reconnected. Please try your query again.")
                    continue

                response = await self.process_query(query)
                print("\n" + response)

            except (asyncio.exceptions.CancelledError, anyio.EndOfStream, anyio.BrokenResourceError) as conn_err: # Catch potential connection errors
                print(f"\nConnection error: {conn_err}. Attempting to reconnect...")
                self.session = None # Mark session as invalid
                try:
                    await self.cleanup() # Close existing resources
                    # Re-initialize exit stack for new connection attempt
                    self.exit_stack = AsyncExitStack()
                    await self.connect_to_server("./server.py") # Reconnect
                    print("Reconnected successfully. Please try your query again.")
                except Exception as reconn_err:
                    print(f"Failed to reconnect: {reconn_err}. Exiting.")
                    break # Exit if reconnection fails
            except Exception as e: # Catch other general errors
                print(f"\nError: {str(e)}")
                # Optionally break or add more specific error handling here

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()


    async def connect_to_server(self, server_script_path: str):
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        tools_response = await self.session.list_tools()
        tools = tools_response.tools
        # print("Connected to server with tools:", [tool for tool in tools]) # (注释掉的代码) 打印连接成功信息和工具列表

        prompts_response = await self.session.list_prompts()
        prompts = prompts_response.prompts
        # print("Connected to server with prompts:", [prompt for prompt in prompts]) # (注释掉的代码) 打印连接成功信息和提示列表

        resources_templates_response = await self.session.list_resource_templates()
        resources = resources_templates_response.resourceTemplates
        # print("Connected to server with resources:", [resource for resource in resources]) # (注释掉的代码) 打印连接成功信息和资源模板列表

async def main():
    client = MCPClient()
    try:
        await client.connect_to_server("./server.py")
        await client.chat_loop()
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

