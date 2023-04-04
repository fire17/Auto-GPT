import browse
import json
import memory as mem
import datetime
import agent_manager as agents
import speak
from config import Config
import ai_functions as ai
from file_operations import read_file, write_to_file, append_to_file, delete_file
from execute_code import execute_python_file
from json_parser import fix_and_parse_json
from duckduckgo_search import ddg
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import time

cfg = Config()


def get_command(response):
    try:
        response_json = fix_and_parse_json(response)
        
        if "command" not in response_json:
            return "Error:" , "Missing 'command' object in JSON"
        
        command = response_json["command"]

        if "name" not in command:
            return "Error:", "Missing 'name' field in 'command' object"
        
        command_name = command["name"]

        # Use an empty dictionary if 'args' field is not present in 'command' object
        arguments = command.get("args", {})

        if not arguments:
            arguments = {}

        return command_name, arguments
    except json.decoder.JSONDecodeError:
        return "Error:", "Invalid JSON"
    # All other errors, return "Error: + error message"
    except Exception as e:
        return "Error:", str(e)

available_commands = {
    "google": {
        "name": "Google",
        "desc": "For when you need to search Google to answer specific questions about current information or find websites.",
        "args": {
            "input": "<search_query>"
        },
        "cmd_id": 1,        
        # Check if the Google API key is set and use the official search method
        # If the API key is not set or has only whitespaces, use the unofficial search method
        "adapter": lambda **args: google_official_search(args["input"]) if cfg.google_api_key and (cfg.google_api_key.strip() if cfg.google_api_key else None) else google_search(args["input"])
    },
    "memory_add": {
        "name": "Memory Add",
        "desc": 'For when you need to write information to long term memory (key-value dictionary). The default key "$time" can be used for sequential memory or when a key is not needed.',
        "args": {
            "key": "<key>",
            "value": "<string>"
        },
        "cmd_id": 2,
        "adapter": lambda **args: commit_memory(args["key"], args["value"])
    },
    "memory_del": {
        "name": "Memory Delete",
        "desc": "For when you need to remove long term memories.",
        "args": {
            "key": "<key>"
        },
        "cmd_id": 3,
        "adapter": lambda **args: delete_memory(args["key"])
    },
    "memory_ovr": {
        "name": "Memory Overwrite",
        "desc": "For when you need to replace a long term memory value.",
        "args": {
            "key": "<key>",
            "value": "<string>"
        },
        "cmd_id": 4,
        "adapter": lambda **args: overwrite_memory(args["key"], args["value"])
    },
    "browse_website": {
        "name": "Browse Website",
        "desc": "For when you need to visit a web page and get a summary from it. Optionally include a specific question you'd like to find the answer to.",
        "args": {
            "url": "<url>",
            "question": "<what_you_want_to_find_on_website>"
        },
        "cmd_id": 5,
        "adapter": lambda **args: browse_website(args["url"], args["question"])
    },
    "start_agent": {
        "name": "Start GPT Agent",
        "desc": "For when you need to start a new ChatGPT3.5 powered agent. Not to be used for web browsing.",
        "args": {
            "name": "<name>",
            "task": "<short_task_desc>",
            "prompt": "<prompt>"
        },
        "cmd_id": 6,
        "adapter": lambda **args: start_agent(args["name"], args["task"], args["prompt"])
    },
    "message_agent": {
        "name": "Message GPT Agent",
        "desc": "For when you need to message an agent. An agent must be started before it can be messaged. If unsure if an agent exists use list agents first.",
        "args": {
            "key": "<key>",
            "message": "<message>"
        },
        "cmd_id": 7,
        "adapter": lambda **args: message_agent(args["key"], args["message"])
    },
    "list_agents": {
        "name": "List GPT Agents",
        "desc": "Used to list current GPT agents.",
        "args": {},
        "cmd_id": 8,
        "adapter": lambda **args: list_agents()
    },
    "delete_agent": {
        "name": "Delete GPT Agent",
        "desc": "Used to delete an agent.",
        "args": {
            "key": "<key>"
        },
        "cmd_id": 9,
        "adapter": lambda **args: delete_agent(args["key"])
    },
    "write_to_file": {
        "name": "Write to file",
        "desc": "Used to write a file to disk.",
        "args": {
            "file": "<file>",
            "text": "<text>"
        },
        "cmd_id": 10,
        "adapter": lambda **args: write_to_file(args["file"], args["text"])
    },
    "read_file": {
        "name": "Read File",
        "desc": "Used to read a file from disk.",
        "args": {
            "file": "<file>"
        },
        "cmd_id": 11,
        "adapter": lambda **args: read_file(args["file"])
    },
    "append_to_file": {
        "name": "Append to file",
        "desc": "Used to add to a file on disk.",
        "args": {
            "file": {"type": str, "desc": "<file>"},
            "text": "<text>"
        },
        "cmd_id": 12,
        "adapter": lambda **args: append_to_file(args["file"], args["text"])
    },
    "delete_file": {
        "name": "Delete File",
        "desc": "Used to delete a file on disk.",
        "args": {
            "file": "<file>"
        },
        "cmd_id": 13,
        "adapter": lambda **args: delete_file(args["file"])
    },    
    "evaluate_code": {
        # TODO: Change these to take in a file rather than pasted code, if
        # non-file is given, return instructions "Input should be a python
        # filepath, write your code to file and try again"
        "name": "Evaluate Code",
        "desc": "Used to analyse and get suggestions to improve some code.",
        "args": {
            "code": "<full_code_string>"
        },
        "cmd_id": 14,
        "adapter": lambda **args: ai.evaluate_code(args["code"])
    },
    "improve_code": {
        "name": "Get Improved Code",
        "desc": "Used to improve an existing code block.",
        "args": {
            "suggestions": "<list_of_suggestions>",
            "code": "<full_code_string>"
        },
        "cmd_id": 15,
        "adapter": lambda **args: ai.improve_code(args["suggestions"], args["code"])
    },
    "write_tests": {
        "name": "Write Tests",
        "desc": "Used to write tests for a block of code.",
        "args": {
            "code": "<full_code_string>",
            "focus": "<list_of_focus_areas>"
        },
        "cmd_id": 16,
        "adapter": lambda **args: ai.write_tests(args["code"], args["focus"])
    },
    "execute_python_file": {
        "name": "Execute Python File",
        "desc": "Used to execute a python file on disk.",
        "args": {
            "file": "<file>"
        },
        "cmd_id": 17,
        "adapter": lambda **args: execute_python_file(args["file"])
    },
    "task_complete": {
        "name": "Task Complete (Shutdown)",
        "desc": "Used when you are finished and shuts down the process.",
        "args": {
            "reason": "<reason>"
        },
        "cmd_id": 18,
        "adapter": lambda **args: shutdown(args["reason"])
    },
    "get_datetime": {
        "name": "Current Datetime",
        "desc": "Used when the current datetime is needed.",
        "args": {},
        "cmd_id": 19,
        "adapter": lambda **args: get_datetime()
    }, 
    "get_url_text_summary": {
        "name": "Url Text Summary",
        "desc": "For when you need to visit a web page and get a summary from it. Optionally include a specific question you'd like to find the answer to.",
        "args": {
            "url": "<url>",
            "question": "<what_you_want_to_find_on_website>"
        },
        "cmd_id": 20,
        "adapter": lambda **args: get_text_summary(args["url"], args["question"] if "question" in args else "Make an executive summery.")
    },
    "get_hyperlinks": {
        "name": "Get Hyperlinks",
        "desc": "Get all the hyperlinks from a given webpage. Used when exploring a webpage",
        "args": {
            "url": "<url>"},
        "cmd_id": 21,
        "adapter": lambda **args: get_hyperlinks(args["url"])
    },
}


def execute_command(command_name, arguments):
    try:
        if command_name in available_commands and available_commands[command_name]:
            if "adapter" in available_commands[command_name]:
                adapter_func = available_commands[command_name]["adapter"]
                if adapter_func is not None:
                    adapter_func(**arguments)
                else:
                    print(" ::: Adapter function is None :::",command_name, ":::", arguments)
            else:
                print(" ::: Adapter function not available :::",command_name, ":::", arguments)
        else:
            print(f"::: Could Not find command {command_name} ::: args: {arguments}")
            #TODO: Add ability to dynamically create and add to available_commands
    # All errors, return "Error: + error message"
    except Exception as e:
        return " ::: Error: " + str(e)


def get_datetime():
    return "Current date and time: " + \
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def google_search(query, num_results=8):
    search_results = []
    for j in ddg(query, max_results=num_results):
        search_results.append(j)

    return json.dumps(search_results, ensure_ascii=False, indent=4)

def google_official_search(query, num_results=8):
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    import json

    try:
        # Get the Google API key and Custom Search Engine ID from the config file
        api_key = cfg.google_api_key
        custom_search_engine_id = cfg.custom_search_engine_id

        # Initialize the Custom Search API service
        service = build("customsearch", "v1", developerKey=api_key)
        
        # Send the search query and retrieve the results
        result = service.cse().list(q=query, cx=custom_search_engine_id, num=num_results).execute()

        # Extract the search result items from the response
        search_results = result.get("items", [])
        
        # Create a list of only the URLs from the search results
        search_results_links = [item["link"] for item in search_results]

    except HttpError as e:
        # Handle errors in the API call
        error_details = json.loads(e.content.decode())
        
        # Check if the error is related to an invalid or missing API key
        if error_details.get("error", {}).get("code") == 403 and "invalid API key" in error_details.get("error", {}).get("message", ""):
            return "Error: The provided Google API key is invalid or missing."
        else:
            return f"Error: {e}"

    # Return the list of search result URLs
    return search_results_links

def browse_website(url, question):
    summary = get_text_summary(url, question)
    links = get_hyperlinks(url)

    # Limit links to 5
    if len(links) > 5:
        links = links[:5]

    result = f"""Website Content Summary: {summary}\n\nLinks: {links}"""

    return result


def get_text_summary(url, question):
    text = browse.scrape_text(url)
    summary = browse.summarize_text(text, question)
    return """ "Result" : """ + summary


def get_hyperlinks(url):
    link_list = browse.scrape_links(url)
    return link_list


def commit_memory(key, value):
    default_key = "$time"
    if key == default_key:
        key = "_"+str(time.time())
    _text = f"""Committing memory (key:value) "{key}":"{value}" """
    mem.permanent_memory[key] = value
    return _text


def delete_memory(key):
    if key in mem.permanent_memory:
        _text = "Deleting memory with key " + str(key)
        mem.permanent_memory.pop(key)
        return _text
    else:
        print("Invalid key, cannot delete memory.")
        return None


def overwrite_memory(key, value):
    if key in mem.permanent_memory:
        _text = "Overwriting memory with key " + \
            str(key) + " and value " + value
        mem.permanent_memory[key] = value
        print(_text)
        return _text
    else:
        print("Invalid key, cannot overwrite memory.")
        return None


def shutdown(reason = None):
    print("Shutting down...")
    if reason:
        print("Provided Reason:",reason)
    quit()


def start_agent(name, task, prompt, model=cfg.fast_llm_model):
    global cfg

    # Remove underscores from name
    voice_name = name.replace("_", " ")

    first_message = f"""You are {name}.  Respond with: "Acknowledged"."""
    agent_intro = f"{voice_name} here, Reporting for duty!"

    # Create agent
    if cfg.speak_mode:
        speak.say_text(agent_intro, 1)
    key, ack = agents.create_agent(task, first_message, model)

    if cfg.speak_mode:
        speak.say_text(f"Hello {voice_name}. Your task is as follows. {task}.")

    # Assign task (prompt), get response
    agent_response = message_agent(key, prompt)

    return f"Agent {name} created with key {key}. First response: {agent_response}"


def message_agent(key, message):
    global cfg
    agent_response = agents.message_agent(key, message)

    # Speak response
    if cfg.speak_mode:
        speak.say_text(agent_response, 1)

    return f"Agent {key} responded: {agent_response}"


def list_agents():
    return agents.list_agents()


def delete_agent(key):
    result = agents.delete_agent(key)
    if not result:
        return f"Agent {key} does not exist."
    return f"Agent {key} deleted."