TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": "Opens any application on the computer. Use this whenever the user asks to open, launch, or start any app.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {"type": "STRING", "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome')"}
            }
        }
    },
    {
        "name": "ui_controller",
        "description": "Controls the INDRA User Interface panels. Use this to open or close specific widgets on the screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING", 
                    "description": "Action to perform: 'open_logs', 'close_logs', 'open_sys', 'close_sys', 'open_vision', 'close_vision', 'open_time', 'close_time', 'open_status', 'close_status', 'open_cmd', 'close_cmd', 'open_upload', 'close_upload', 'open_all', 'close_all', 'open_remote', 'open_controls', 'close_controls'"
                }
            }
        }
    },
    {
        "name": "save_memory",
        "description": "Saves a piece of information to long-term memory.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {"type": "STRING", "description": "Category of memory (e.g., user_pref, fact)"},
                "key": {"type": "STRING", "description": "Short key for the info"},
                "value": {"type": "STRING", "description": "The information to remember"}
            }
        }
    },
    {
        "name": "weather_report",
        "description": "Fetches the current weather report.",
        "parameters": {"type": "OBJECT", "properties": {"location": {"type": "STRING"}}}
    },
    {
        "name": "system_monitor",
        "description": "Retrieves current system resource usage (CPU, RAM, GPU, etc.).",
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "media_control",
        "description": "Controls system media playback.",
        "parameters": {"type": "OBJECT", "properties": {"command": {"type": "STRING", "description": "'play', 'pause', 'next', 'prev'"}}}
    },
    {
        "name": "autopilot",
        "description": "Engages AutoPilot mode to automate complex tasks on the computer.",
        "parameters": {"type": "OBJECT", "properties": {"goal": {"type": "STRING", "description": "The goal to achieve"}}}
    },
    {
        "name": "clipboard_tool",
        "description": "Interacts with the system clipboard.",
        "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "description": "'read' or 'write'"}, "text": {"type": "STRING", "description": "Text to write (if writing)"}}}
    },
    {
        "name": "window_controller",
        "description": "Manipulates active windows on the screen.",
        "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING"}, "window_name": {"type": "STRING"}}}
    },
    {
        "name": "db_memory_manager",
        "description": "Manages database memory items.",
        "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING"}, "query": {"type": "STRING"}}}
    },
    {
        "name": "intelligence_agent",
        "description": "Spawns a sub-agent to fetch intelligence or perform deep research.",
        "parameters": {"type": "OBJECT", "properties": {"query": {"type": "STRING"}}}
    },
    {
        "name": "system_diagnostics",
        "description": "Runs system diagnostics and health checks.",
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "email_agent",
        "description": "Handles sending or reading emails.",
        "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING"}, "recipient": {"type": "STRING"}, "body": {"type": "STRING"}}}
    },
    {
        "name": "camera_vision",
        "description": "Captures a frame from the webcam for visual analysis.",
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "document_maker",
        "description": "Generates a document based on a topic.",
        "parameters": {"type": "OBJECT", "properties": {"topic": {"type": "STRING"}}}
    },
    {
        "name": "image_editor",
        "description": "Opens the image editor or edits an image.",
        "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING"}}}
    },
    {
        "name": "terminal_controller",
        "description": "Executes terminal commands.",
        "parameters": {"type": "OBJECT", "properties": {"command": {"type": "STRING"}}}
    },
    {
        "name": "spotify_controller",
        "description": "Controls Spotify.",
        "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING"}}}
    },
    {
        "name": "agent_cron",
        "description": "Schedules tasks or alarms.",
        "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING"}, "time": {"type": "STRING"}}}
    },
    {
        "name": "python_executor",
        "description": "Executes Python code.",
        "parameters": {"type": "OBJECT", "properties": {"code": {"type": "STRING"}}}
    },
    {
        "name": "network_scanner",
        "description": "Scans the network.",
        "parameters": {"type": "OBJECT", "properties": {}}
    }
]
