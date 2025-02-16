from openai import OpenAI
import controls as controller
import json

# Initialize the OpenAI client and controls instance
client = OpenAI()
controls = controller.Controls()

def call_function(name, arguments=None):
    # arguments can be a dict with additional parameters
    if name == "turn_left":
        # If you want to use the 'degrees' parameter:
        degrees = arguments.get("degrees") if arguments else 90
        # You can pass degrees to controls.turn_left(degrees) if your method supports it.
        controls.turn_left(degrees)
    elif name == "turn_right":
        degrees = arguments.get("degrees") if arguments else 90
        controls.turn_right(degrees)
    elif name == "go_forward":
        speed = arguments.get("speed") if arguments else 100
        controls.go_forward(speed)
    elif name == "go_backward":
        speed = arguments.get("speed") if arguments else 20
        controls.go_backward(speed)
    else:
        print("No matching function for", name)

tools = [
    {
        "id": "call_turn_left",
        "type": "function",
        "function": {
            "name": "turn_left",
            "parameters": {
                "type": "object",
                "properties": {
                    "degrees": {
                        "type": "number",
                        "description": "Number of degrees to turn left default is 90",
                    }
                }
            },
            "required": ["degrees"]
        }
    },
    {
        "id": "call_turn_right",
        "type": "function",
        "function": {
            "name": "turn_right",
            "parameters": {
                "type": "object",
                "properties": {
                    "degrees": {
                        "type": "number",
                        "description": "Number of degrees to turn right",
                        "default": -90
                    }
                }
            },
            "required": ["degrees"]
        }
    },
    {
        "id": "call_go_forward",
        "type": "function",
        "function": {
            "name": "go_forward",
            "parameters": {
                "type": "object",
                "properties": {
                    "speed": {
                        "type": "number",
                        "description": "Speed as a percentage of the maximum speed",
                        "default": 100
                    },
                    "duration": {
                        "type": "number",
                        "description": "Duration in seconds",
                    }
                }
            },
            "required": ["speed", "duration"],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "id": "call_go_backward",
        "type": "function",
        "function": {
            "name": "go_backward",
            "parameters": {
                "type": "object",
                "properties": {
                    "speed": {
                        "type": "number",
                        "description": "Speed as a percentage of the maximum speed",
                        "default": 100
                    }
                }
            },
            "required": ["speed"]
        }
    },
]

while True:
    # Get command from the user
    message = input("Enter your command: ")
    if message.lower() == "exit":
        break

    # Create a chat completion with the provided message and tools
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{'role': 'user', 'content': message}],
        tools=tools
    )

    # Check if there's a tool call and execute the corresponding function
    try:
        if completion.choices[0].message.tool_calls:
            tool_call = completion.choices[0].message.tool_calls[0]
            print("Tool call received:", tool_call)
            function_name = tool_call.function.name

            raw_args = tool_call.function.arguments if hasattr(tool_call.function, "arguments") else "{}"
        if isinstance(raw_args, str):
            try:
                arguments = json.loads(raw_args)
            except json.JSONDecodeError:
                arguments = {}
        else:
            arguments = raw_args
        
        print("Function called:", function_name, "with arguments:", arguments)
        if function_name:
            call_function(function_name, arguments)
            
        else:
            print("No tool call received. Full response:", completion)
    except (IndexError, AttributeError) as e:
        print("Error processing tool call:", e) 
