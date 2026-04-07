"""
Tool Registry Module
Defines and registers capable tools that Miku's AI Brain can invoke.
Follows the Agentic Harness pattern for clean tool isolation.
"""

from typing import Dict, Any, Callable, List
import inspect
from pydantic import BaseModel, create_model
from typing import get_type_hints

class ToolParam:
    def __init__(self, name: str, param_type: type, description: str, required: bool = True):
        self.name = name
        self.param_type = param_type
        self.description = description
        self.required = required

class Tool:
    def __init__(self, name: str, description: str, func: Callable):
        self.name = name
        self.description = description
        self.func = func
        self.params: List[ToolParam] = []
        
        # Parse signature
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)
        
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
                
            param_type = type_hints.get(param_name, str)
            is_required = param.default == inspect.Parameter.empty
            
            # Simple description extraction from docstring could be added here, 
            # for now we'll just use the param name
            param_desc = f"Parameter: {param_name}"
            
            self.params.append(ToolParam(
                name=param_name, 
                param_type=param_type, 
                description=param_desc, 
                required=is_required
            ))

    def to_openai_schema(self) -> Dict[str, Any]:
        """Convert tool definition to OpenAI/Qwen compatible JSON Schema"""
        properties = {}
        required = []
        
        for param in self.params:
            # Map Python types to JSON Schema types
            type_str = "string"
            if param.param_type == int: type_str = "integer"
            elif param.param_type == float: type_str = "number"
            elif param.param_type == bool: type_str = "boolean"
            
            properties[param.name] = {
                "type": type_str,
                "description": param.description
            }
            if param.required:
                required.append(param.name)
                
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }
        
    def execute(self, instance, **kwargs):
        """Execute the tool function"""
        # If it's a method taking self, pass the instance
        if 'self' in inspect.signature(self.func).parameters:
            return self.func(instance, **kwargs)
        return self.func(**kwargs)


class ToolRegistry:
    """Central registry for all AI tools"""
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        
    def register(self, description: str = None, name: str = None):
        """Decorator to register a method as a tool"""
        def decorator(func):
            tool_name = name or func.__name__
            desc = description or func.__doc__ or f"Tool: {tool_name}"
            desc = desc.strip()
            
            tool = Tool(name=tool_name, description=desc, func=func)
            self._tools[tool_name] = tool
            return func
        return decorator
        
    def register_manual(self, name: str, description: str, func: Callable):
        """Manually register a tool"""
        tool = Tool(name=name, description=description, func=func)
        self._tools[name] = tool
        
    def get_tool(self, name: str) -> Tool:
        return self._tools.get(name)
        
    def get_all_tools_schema(self) -> List[Dict[str, Any]]:
        """Get schema for all registered tools, ready for LLM"""
        return [tool.to_openai_schema() for tool in self._tools.values()]
        
    def execute(self, tool_name: str, instance: Any, kwargs: Dict[str, Any]) -> Any:
        """Execute a tool by name and return result"""
        tool = self.get_tool(tool_name)
        if not tool:
            return False, f"Error: Tool '{tool_name}' not found in registry."
            
        try:
            print(f"[ToolRegistry] Executing {tool_name} with args {kwargs}")
            # The execution returns various types based on old SystemControl
            # Usually Tuple[bool, str]
            return tool.execute(instance, **kwargs)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Error executing {tool_name}: {str(e)}"

# Global registry instance
registry = ToolRegistry()
