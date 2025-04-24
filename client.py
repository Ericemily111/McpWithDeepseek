import asyncio
from typing import Optional
from contextlib import AsyncExitStack
import ipdb
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from openai import OpenAI
# from dotenv import load_dotenv

# load_dotenv()  # load environment variables from .env

class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.client =  OpenAI(api_key="sk-", base_url="https://api.deepseek.com")
        # print(self.client)
        self.messages = []
        print('a')

    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server
        
        Args:
            server_script_path: Path to the server script (.py or .js)
        """
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
        
        # List available tools
        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:", [tool.name for tool in tools])

    async def process_query(self, query: str) -> str:
        """Process a query using OpenAI and available tools"""

        self.messages.append({"role": "user","content": query})

        # response = await self.session.list_tools()


        available_tools = [{ 
            "type": "function",
            "function": {
                "name": "get_alerts",
                "description": "Get weather alerts for a US state.",
                "parameters":{
                    "type": "object",
                    "properties": {
                        "state": {
                            "type": "string",
                            "description": "The state, e.g. CA",
                        }
                    },
                    "required": ["state"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_forecast",
                "description": "Get weather forecast for a location.",
                "parameters":{
                    "type": "object",
                    "properties": {
                        "latitude": {
                            "type": "number",
                            "description": "The latitude of the city, e.g., 30.2741 for Hangzhou (positive for N, negative for S)"
                        },
                        "longitude": {
                            "type": "number",
                            "description": "The longitude of the city, e.g., 120.1552 for Hangzhou (positive for E, negative for W)"
                        }
                    },
                    "required": ["latitude","longitude"]
                }
            }
        }]

        # print(f"tools:{response.tools}")

        # Initial OpenAI API call
        response = self.client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=1000,
            messages=self.messages,
            tools=available_tools
        )


        message = response.choices[0].message

        # Process tool calls
        if message.tool_calls:
            # Append the assistant message with tool_calls
            self.messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [{
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments
                    }
                } for tool_call in message.tool_calls]
            })

            # Execute each tool call and append tool responses
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                result = await self.session.call_tool(tool_name, tool_args)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result.content[0].text
                })
            # Second OpenAI API call with tool results
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                max_tokens=1000,
                messages=self.messages,
                tools=available_tools
            )
            message = response.choices[0].message

            return message.content + "\n"
        else:
            return "the tool is not used\n"
        
        

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")
        
        while True:
            try:
                query = input("\nQuery: ").strip()
                
                if query.lower() == 'quit':
                    break
                    
                response = await self.process_query(query)
                print("\n" + response)
                    
            except Exception as e:
                print(f"\nError: {str(e)}")
    
    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()

async def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script>")
        sys.exit(1)
        
    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    import sys
    # print('1')
    asyncio.run(main())