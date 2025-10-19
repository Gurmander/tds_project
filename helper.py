import os
import time 
from dotenv import load_dotenv
import requests
import base64
import json
import textwrap

load_dotenv()

# os.getenv() for sec
secret_key = os.getenv('MY_SECRET')
api_token = os.getenv('API_TOKEN')
gh_token = os.getenv('GITHUB_TOKEN')
gh_user = os.getenv('GITHUB_USERNAME')



def verify_secret(test):
    return test == secret_key



# -------------------- GIT REPO STUFF ---------------------------
def check_repo_exists(repo_name: str) -> bool:
    """Check if a GitHub repository exists"""
    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json"
    }
    
    response = requests.get(
        f"https://api.github.com/repos/{gh_user}/{repo_name}",
        headers=headers
    )
    
    return response.status_code == 200




def create_github_repo(repo_name: str, force_recreate: bool):
    # create repo w/ given repo name

    # Check if repo exists and delete if force_recreate is True
    if force_recreate and check_repo_exists(repo_name):
        print(f"🔄 Repo '{repo_name}' already exists. Deleting...")
        delete_github_repo(repo_name)
        
        # Wait a moment for GitHub to process the deletion
        time.sleep(2)
        print("⏳ Waiting for deletion to complete...")


    payload = {
        "name": repo_name,
        "private": False,
        "auto_init": True,
        "license_template": "mit",        
    }
    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json"
    }

    # make sure git_token admin permission w/ R & W is added
    response = requests.post(
        "https://api.github.com/user/repos",
        headers=headers,
        json=payload
    )

    if response.status_code == 201:
        print(f"✅ Successfully created repo: {repo_name}")
        return response.json()
    elif response.status_code == 422:
        # Repo still exists (deletion might not have completed)
        print(f"⚠️ Repo still exists. Retrying deletion...")
        delete_github_repo(repo_name)
        time.sleep(3)
        
        # Retry creation
        response = requests.post(
            "https://api.github.com/user/repos",
            headers=headers,
            json=payload
        )
        
        if response.status_code == 201:
            print(f"✅ Successfully created repo on retry: {repo_name}")
            return response.json()
        else:
            raise Exception(f"Failed to create repo after retry: {response.status_code}: {response.text}")
    else:
        raise Exception(f"Failed to create repo: {response.status_code}: {response.text}")




def enable_github_pages(repo_name: str):
    """Enable GitHub Pages for the repository"""
    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json"
    }
    
    payload = {
        "source": {
            "branch": "main",
            "path": "/"
        }
    }
    
    response = requests.post(
        f"https://api.github.com/repos/{gh_user}/{repo_name}/pages",
        headers=headers,
        json=payload
    )
    
    if response.status_code == 201:
        pages_url = response.json().get("html_url", f"https://{gh_user}.github.io/{repo_name}/")
        print(f"GitHub Pages enabled successfully!")
        print(f"Site will be available at: {pages_url}")
        print(f"Note: It may take a few minutes for the site to be published.")
        # return response.json()
        return pages_url
    elif response.status_code == 409:
        # Pages already enabled, get the current status
        get_response = requests.get(
            f"https://api.github.com/repos/{gh_user}/{repo_name}/pages",
            headers=headers
        )
        if get_response.status_code == 200:
            pages_url = get_response.json().get("html_url", f"https://{gh_user}.github.io/{repo_name}/")
            print(f"GitHub Pages already enabled at: {pages_url}")
            return get_response.json()
        else:
            raise Exception(f"Pages already enabled but failed to get info: {get_response.status_code}: {get_response.text}")
    else:
        raise Exception(f"Failed to enable github pages: {response.status_code}: {response.text}")



def push_files_to_repo(repo_name, files: list[dict], round:int):
    # push files to github repo
    if round == 2:
        latest_sha = get_sha_of_latest_commit(repo_name)
    else:
        latest_sha = None
    # TODO : use cli to push
    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json"
    }    

    # Step 1: Get the current commit SHA (HEAD of default branch)
    repo_response = requests.get(
        f"https://api.github.com/repos/{gh_user}/{repo_name}",
        headers=headers
    )
    if repo_response.status_code != 200:
        raise Exception(f"Failed to get repo info: {repo_response.status_code}, {repo_response.text}")
    

    default_branch = repo_response.json()["default_branch"]


    # Get the latest commit SHA with retry logic (in case repo was just created)
    max_retries = 5
    ref_response = None
    for attempt in range(max_retries):
        ref_response = requests.get(
            f"https://api.github.com/repos/{gh_user}/{repo_name}/git/ref/heads/{default_branch}",
            headers=headers
        )
        if ref_response.status_code == 200:
            break
        if attempt < max_retries - 1:
            print(f"Waiting for branch to be ready... (attempt {attempt + 1}/{max_retries})")
            time.sleep(2)
    
    if ref_response.status_code != 200:
        raise Exception(f"Failed to get branch ref: {ref_response.status_code}, {ref_response.text}")    


    latest_commit_sha = ref_response.json()["object"]["sha"]    

    # Step 2: Get the tree SHA from the latest commit
    commit_response = requests.get(
        f"https://api.github.com/repos/{gh_user}/{repo_name}/git/commits/{latest_commit_sha}",
        headers=headers
    )
    if commit_response.status_code != 200:
        raise Exception(f"Failed to get commit: {commit_response.status_code}, {commit_response.text}")
    
    base_tree_sha = commit_response.json()["tree"]["sha"]    

    # Step 3: Create blobs for each file
    tree_items = []
    for file in files:
        file_name = file.get("name")
        file_content = file.get("content")
        
        # Convert content to base64 if needed
        if isinstance(file_content, bytes):
            content_encoded = base64.b64encode(file_content).decode("utf-8")
        else:
            content_encoded = base64.b64encode(file_content.encode("utf-8")).decode("utf-8")
        
        # Create blob
        blob_payload = {
            "content": content_encoded,
            "encoding": "base64"
        }
        blob_response = requests.post(
            f"https://api.github.com/repos/{gh_user}/{repo_name}/git/blobs",
            headers=headers,
            json=blob_payload
        )
        if blob_response.status_code != 201:
            raise Exception(f"Failed to create blob for {file_name}: {blob_response.status_code}, {blob_response.text}")
        
        blob_sha = blob_response.json()["sha"]
        
        # Add to tree
        tree_items.append({
            "path": file_name,
            "mode": "100644",  # regular file
            "type": "blob",
            "sha": blob_sha
        })

    # Step 4: Create a new tree
    tree_payload = {
        "base_tree": base_tree_sha,
        "tree": tree_items
    }
    tree_response = requests.post(
        f"https://api.github.com/repos/{gh_user}/{repo_name}/git/trees",
        headers=headers,
        json=tree_payload
    )
    if tree_response.status_code != 201:
        raise Exception(f"Failed to create tree: {tree_response.status_code}, {tree_response.text}")
    
    new_tree_sha = tree_response.json()["sha"]
    
    # Step 5: Create a new commit
    commit_payload = {
        "message": f"Round {round}: Add/Update {len(files)} file(s)",
        "tree": new_tree_sha,
        "parents": [latest_commit_sha]
    }
    new_commit_response = requests.post(
        f"https://api.github.com/repos/{gh_user}/{repo_name}/git/commits",
        headers=headers,
        json=commit_payload
    )
    if new_commit_response.status_code != 201:
        raise Exception(f"Failed to create commit: {new_commit_response.status_code}, {new_commit_response.text}")
    
    new_commit_sha = new_commit_response.json()["sha"]
    
    # Step 6: Update the reference to point to the new commit
    update_ref_payload = {
        "sha": new_commit_sha,
        "force": False  # Set to True if you want to force push
    }
    update_ref_response = requests.patch(
        f"https://api.github.com/repos/{gh_user}/{repo_name}/git/refs/heads/{default_branch}",
        headers=headers,
        json=update_ref_payload
    )
    if update_ref_response.status_code != 200:
        raise Exception(f"Failed to update ref: {update_ref_response.status_code}, {update_ref_response.text}")
    
    print(f"Successfully pushed {len(files)} files in commit {new_commit_sha}")
    return new_commit_sha


# Delete repo on failure
def delete_github_repo(repo_name: str):
    """Delete a GitHub repository"""
    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json"
    }
    
    response = requests.delete(
        f"https://api.github.com/repos/{gh_user}/{repo_name}",
        headers=headers
    )
    
    if response.status_code == 204:
        print(f"✅ Successfully deleted repo: {repo_name}")
        return True
    elif response.status_code == 404:
        print(f"⚠️ Repo {repo_name} not found (may not have been created)")
        return False
    else:
        print(f"❌ Failed to delete repo: {response.status_code}: {response.text}")
        return False



def get_current_repo_files(repo_name: str) -> dict:
    """
    Fetch all current files from the repository
    Returns dict with filename: content
    """
    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json"
    }
    
    def get_files_recursive(path=""):
        """Recursively get all files from repo"""
        response = requests.get(
            f"https://api.github.com/repos/{gh_user}/{repo_name}/contents/{path}",
            headers=headers
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get files at {path}: {response.status_code}")
        
        items = response.json()
        files = {}
        
        for item in items:
            if item['type'] == 'file':
                # Get file content
                file_response = requests.get(item['download_url'])
                if file_response.status_code == 200:
                    files[item['path']] = file_response.text
            elif item['type'] == 'dir':
                # Recursively get files from subdirectory
                subdir_files = get_files_recursive(item['path'])
                files.update(subdir_files)
        
        return files
    
    return get_files_recursive()


def get_default_gitignore() -> str:
    """Return comprehensive .gitignore content"""
    return """# Environment variables
.env
.env.local
.env.*.local

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
ENV/
.venv

# Node
node_modules/
npm-debug.log
yarn-error.log
.pnpm-debug.log

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Build
dist/
build/
*.egg-info/

# Secrets
*.pem
*.key
secrets/
credentials/
"""


# sha required if want to update file, in round 2
def get_sha_of_latest_commit(repo_name: str, branch: str = "main") -> str:
    response = requests.get(f"https://api.github.com/repos/{gh_user}/{repo_name}/commits/{branch}")
    if response.status_code != 200:
        raise Exception("Failed to get latest commit sha: {response.status_code}, {response.text}")
    return response.json().get("sha")




# -------------------- GIT REPO STUFF --------------------------- #


# -------------------------- LLM --------------------------- 
def call_aipipe_llm(messages: list=[], model: str = "gpt-4o-mini") -> str:
    
    url = "https://aipipe.org/openrouter/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 8000
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=500)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract the message content from OpenAI-format response
        if 'choices' in data and len(data['choices']) > 0:
            return data['choices'][0]['message']['content']
        else:
            raise Exception(f"Unexpected response format: {data}")
            
    except requests.exceptions.RequestException as e:
        raise Exception(f"Error calling aipipe API: {str(e)}")



def write_code_with_llm(task_data: dict) -> dict:
    
    print("🧠 Calling API to create round 1 code...")
    # Extract task information
    task_id = task_data.get('task', 'unknown-task')
    brief = task_data.get('brief', '')
    checks = task_data.get('checks', [])
    
    # Format checks
    checks_formatted = "\n".join([f"{i+1}. {check}" for i, check in enumerate(checks)])
    
    system_prompt = f" You are a highly skilled web developer specializing in full-stack development. Your objective is to create a complete single-page web application according to the specifications provided. "
    prompt = f""" 
    You must create a standalone index.html file containing all required HTML markup, CSS styling, and JavaScript functionality.
    If external libraries such as Bootstrap, jQuery etc. are required, incorporate them using CDN (Content Delivery Network) links.
    The code you produce must be accurate, functional, and ready for immediate use without modifications. If any error, handle them gracefully.      

    TASK: {task_id}
    DESCRIPTION: {brief}

    REQUIREMENTS (ALL must be met):
    {checks_formatted}

    ATTACHMENTS:
        - If any attachment of type image_url is provided, include it in the generated HTML using its exact image_url value as:
        <img src="data:image/..."> 
        Add appropriate styling (responsive layout, borders, etc.) as needed to fit the design.
        - Do NOT alter, truncate, or replace the image URL.
        - For non-image attachments, process them according to the provided handling rules.


    FILE REQUIREMENTS:
    1. index.html - Complete working app at root (not in subfolder)
    3. README.md - Professional, with:
    - Project summary
    - How to use (open index.html or GitHub Pages URL)
    - How to pass URL parameters (?url=...)
    - MIT License included
    4. .gitignore - Basic ignore file

    CODE QUALITY:
    • Write COMPLETE, FUNCTIONAL code (no TODOs or placeholders)
    • Handle errors gracefully

    OUTPUT FORMAT (CRITICAL - PURE JSON ONLY):
    Return ONLY this JSON structure with no markdown code blocks, no explanatory comments or any wrapper text.
    DO NOT ADD ANY COMMENTS. 

    {{
    "files": {{
        "index.html": "<!DOCTYPE html>\\n<html lang=\\"en\\">\\n<head>...</head>\\n<body>...</body>\\n</html>",
        "README.md": "# Project Title\\n\\n## Summary\\n...\\n## License\\nMIT License...",
        ".gitignore": "node_modules/\\n.env\\n.DS_Store"
    }},
    "description": "Brief one-line description"
    }}

    IMPORTANT: Return the raw JSON object only, with COMPLETE file contents. Do not use markdown code blocks or any wrapper text.

    EXAMPLE for index.html:
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{task_id}</title>
    <style>/* CSS here */</style>
    </head>
    <body>
    <h1>App Title</h1>
    <div id="app"><!-- Content --></div>
    <script>
        // All JavaScript here or link external file
    </script>
    </body>
    </html>
    """


    content = build_multimodal_messages(prompt, task_data.get('attachments'))

    try:
        print(f"📝 Prompt length: {len(prompt)} characters")
        
        # Call LLM API
        print("🤖 Calling LLM...")
        messages = [
            {"role": "system", "content": [{"type": "text", "text": system_prompt} ]},
            content
        ]
        response_text = call_aipipe_llm(messages)
        
        # Parse JSON from response
        print("🔍 Extracting JSON...")
        code_structure = extract_json_from_response(response_text)
        
        # Validate structure
        if not isinstance(code_structure, dict):
            raise ValueError("LLM response is not a dictionary")
        
        if "files" not in code_structure:
            raise ValueError("LLM response missing 'files' key")
        
        if not isinstance(code_structure["files"], dict):
            raise ValueError("'files' is not a dictionary")
        
        
        # Ensure index.html exists
        if "index.html" not in code_structure["files"]:
            raise ValueError("Missing required 'index.html' file")
        
        
        # Ensure .gitignore exists
        if ".gitignore" not in code_structure["files"]:
            code_structure["files"][".gitignore"] = get_default_gitignore()
        
        # Log success
        print(f"✅ Code generated successfully!")
        print(f"   Files created: {len(code_structure['files'])}")
        for filename, content in code_structure["files"].items():
            print(f"   - {filename}: {len(content)} characters")
        
        return code_structure
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing failed: {e}")
        print(f"   Response length: {len(response_text)}")
        print(f"   First 200 chars: {response_text[:200]}")
        print(f"   Last 200 chars: {response_text[-200:]}")
        
        raise Exception(f"Error parsing LLM JSON response: {str(e)}")
        
    except Exception as e:
        print(f"❌ Error generating code: {e}")
        raise Exception(f"Error generating code with LLM: {str(e)}")



def write_code_update_with_llm(task_data: dict, current_files: dict) -> dict:

    print("🧠 Calling API for round 2 ...")
    task_id = task_data.get('task', 'unknown-task')
    brief = task_data.get('brief', '')
    checks = task_data.get('checks', [])
    
    checks_formatted = "\n".join([f"- {check}" for check in checks])
    

    current_files_formatted = []
    for filename, content in current_files.items():
        current_files_formatted.append(f"=== {filename} ===\n{content}")
    
    current_files_str = "\n\n".join(current_files_formatted)
    
    system_prompt = f"""
    You are an expert full-stack developer updating an existing code based on new briefs.
    Do not add any comments, just provide final, complete, updated code. Make sure code is ready for production deployment, handle errors gracefully.
    """

 
    prompt = f"""
    
    YOUR TASK:
        1. Analyze current code thoroughly. Check the README.md file to see what was done previously.
        2. Identify required updates based on briefs
        3. Generate COMPLETE updated files with full content
        4. Verify all evaluation criteria will pass
        5. Handle any attachments as mentioned.
    
    TASK ID: {task_id}
    ROUND: 2 (Update existing code)

    CURRENT APPLICATION FILES: 
    {current_files_str}

    NEW REQUIREMENTS:
    {brief}

    
    EVALUATION CRITERIA (ALL must pass):
    {checks_formatted}


    CRITICAL REQUIREMENTS:

    1. FILE STRUCTURE:
    - index.html MUST be at repository root (not in subdirectories)
    - Maintain consistent code structure

    2. CODE QUALITY:
    - Return COMPLETE file contents (not diffs or partial updates)
    - NO placeholders or TODO comments
    - Production-ready, tested code
    - Ensure all evaluation criteria pass

    5. DOCUMENTATION:
    - Keep README.md professional and comprehensive
    - Update all sections affected by in README.md
    - Document new features and requirements



    RESPONSE FORMAT (valid JSON only):
    {{
        "files": {{
            "index.html": "complete updated HTML content",
            "README.md": "complete updated README content",
            ".gitignore": "standard gitignore content",
        }},
        "description": "Concise description of changes made",
    }}

    IMPORTANT: Return the raw JSON object only, with COMPLETE file contents. Do not use markdown code blocks or any wrapper text."""

    content = build_multimodal_messages(prompt, task_data.get('attachments'))

    try:
        print(f"📝 Prompt length: {len(prompt)} characters")
        
        # Call LLM API
        print("🤖 Calling LLM...")
        messages = [
            {"role": "system", "content": [{"type": "text", "text": system_prompt} ]},
            content
        ]
        response_text = call_aipipe_llm(messages)

        code_structure = extract_json_from_response(response_text)
        
        print(f"✅ CODE UPDATED SUCCESSFULLY")
        
        return code_structure
        
    except Exception as e:
        raise Exception(f"Error updating code with LLM: {str(e)}")



# -------------------------- LLM --------------------------- #


# -------------------------- PROCESS ATTACHMENTS -----------------------


def build_multimodal_messages(prompt_text: str, attachments: list, chunk_size: int = 5000):
    """
    Build a multimodal messages array for OpenRouter/OpenAI chat API.

    Parameters:
    - prompt_text: str → main instructions / task description
    - attachments: list of dicts {"name": ..., "url": base64 string}
    - chunk_size: int → max characters per chunk for large text files

    Returns:
    - messages: list of dicts ready for API
    """

    content = [{"type": "text", "text": prompt_text}]

    for attachment in attachments:
        filename = attachment.get("name", "unknown")
        base64_data = attachment.get("url", "")
        ext = filename.split(".")[-1].lower()

        try:
            # --- Text files ---
            if ext in ["txt", "csv", "json"]:
                decoded_bytes = base64.b64decode(base64_data.split(",", 1)[-1])
                text_content = decoded_bytes.decode("utf-8", errors="ignore")

                # Chunk large text to avoid token overflow
                if len(text_content) > chunk_size:
                    chunks = [text_content[i:i+chunk_size] for i in range(0, len(text_content), chunk_size)]
                    for i, chunk in enumerate(chunks, 1):
                        content.append({
                            "type": "text",
                            "text": f"[CHUNK {i}/{len(chunks)} - {filename}]\n{chunk}"
                        })
                else:
                    content.append({"type": "text", "text": f"[FILE: {filename}]\n{text_content}"})

            # --- Image files ---
            elif ext in ["png", "jpg", "jpeg", "gif", "webp"]:
                data_uri = f"data:image/{ext};base64,{base64_data.split(',',1)[-1]}"
                content.append({"type": "image_url", "image_url": data_uri})
                print("Image Data ::::: \n", data_uri[:40])

            # --- Binary / large unknown files ---
            else:
                size_kb = len(base64_data) * 3 / 4 / 1024
                content.append({
                    "type": "text",
                    "text": f"[BINARY FILE: {filename} ~{size_kb:.1f} KB] - include externally if needed"
                })

        except Exception as e:
            # In case decoding fails, include metadata as text
            content.append({
                "type": "text",
                "text": f"[ERROR PROCESSING FILE: {filename}] - {str(e)}"
            })

    # Return as a single user message
    return {"role": "user", "content": content}


# -------------------------- CODE STRUCTURE ---------------------------
def handle_query(data):

    repo_name = f"{data['task'].replace(' ', '-')}-{data['nonce']}"
    max_tries = 3
    try:
        for i in range(max_tries):
            try:
                if data.get('round') ==1:
                    # test_api_connection()
                    # get attachments
                    code_structure = write_code_with_llm(data)
                    files = []
                    for filename, content in code_structure["files"].items():
                        files.append({
                            "name": filename,
                            "content": content
                        })
                    create_github_repo(repo_name, True)
                    pages_url = enable_github_pages(repo_name)
                    latest_sha = push_files_to_repo(repo_name, files, 1)
                    obj = {
                        "email": data.get('email'),
                        "task": data.get('task'),
                        "round": data.get('round'),
                        "nonce": data.get('nonce'),
                        "repo_url": f"https://api.github.com/repos/{gh_user}/{repo_name}",
                        "commit_sha": latest_sha,
                        "pages_url": pages_url,
                    }

                    evaluation_url = data.get('evaluation_url')
                    hit_evaluation_url(evaluation_url, obj)
                    print("Round 1 Successfull")
                    break

                else:
                    handle_round_2(data)     
                    print("Round 2 Successfull")    
                    break

            except Exception as e:
                print(f"Error occurred while handling query, Attempt {i+1}/{max_tries}: {e}")
                if i == max_tries - 1:  # Last attempt failed
                    print("All retry attempts exhausted")
                    raise  # Re-raise the exception after final attempt
        

    except Exception as e:
        print(f"❌ ERROR in round_1: {str(e)}")
        print(f"🧹 Cleaning up - attempting to delete repo: {repo_name}")
        
        # Attempt cleanup if round 1
        if data.get('round') ==1:
            delete_github_repo(repo_name)
        
        # Re-raise the exception so caller knows it failed
        raise Exception(f"round_1 failed: {str(e)}")        


def extract_json_from_response(response_text: str) -> dict:
    """
    Robustly extract and parse JSON from LLM response.
    Handles multiple formats: pure JSON, markdown code blocks, mixed content.
    """
    import re
    
    # Strategy 1: Try to find JSON in ```json code blocks
    json_pattern = r'```json\s*(\{.*?\})\s*```'
    matches = re.findall(json_pattern, response_text, re.DOTALL)
    if matches:
        # Take the last JSON block (most likely the final answer)
        try:
            return json.loads(matches[-1])
        except json.JSONDecodeError:
            pass  # Fall through to next strategy
    
    # Strategy 2: Try to find JSON in any ``` code blocks
    code_block_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
    matches = re.findall(code_block_pattern, response_text, re.DOTALL)
    if matches:
        for match in reversed(matches):  # Try from last to first
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue
    
    # Strategy 3: Try to find a JSON object anywhere in the text
    json_object_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    matches = re.findall(json_object_pattern, response_text, re.DOTALL)
    if matches:
        for match in reversed(matches):  # Try from last to first
            try:
                parsed = json.loads(match)
                # Validate it has expected structure
                if isinstance(parsed, dict) and 'files' in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue
    
    # Strategy 4: Try parsing the entire response as JSON
    try:
        return json.loads(response_text.strip())
    except json.JSONDecodeError:
        pass
    
    # If all strategies fail, raise a clear error
    raise ValueError(
        "Could not extract valid JSON from LLM response. "
        "Response preview: " + response_text[:500]
    )    


def hit_evaluation_url(evaluation_url, eval_obj):
    # Extract evaluation URL
    if not evaluation_url:
        return {"Error": "Missing evaluation_url"}

    # Send with retry + exponential backoff
    max_retries = 5
    delay = 1  # seconds

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(evaluation_url, json=eval_obj, timeout=10)

            if response.status_code == 200:
                return {
                    "Data": "Sent",
                    "Status": response.status_code,
                    "Response": response.text,
                    "Attempts": attempt
                }

            # non-200 → log and retry
            print(f"[Attempt {attempt}] Non-200: {response.status_code}, retrying in {delay}s")
        except requests.RequestException as e:
            print(f"[Attempt {attempt}] Request failed: {e}, retrying in {delay}s")

        # wait before retrying
        time.sleep(delay)
        delay *= 2  # exponential backoff (1, 2, 4, 8, ...)

    return {"Error": f"Failed after {max_retries} retries"}    


def handle_round_2(data):
    """Handle round 2 - update existing repo based on feedback"""
    repo_name = f"{data['task'].replace(' ', '-')}-{data['nonce']}"
    
    try:
        print(f"🔄 Starting Round 2 for {repo_name}")
        
        # Step 1: Get current files from repo
        print("📥 Fetching current files from repo...")
        current_files = get_current_repo_files(repo_name)
        print(f"✅ Found {len(current_files)} files")
        
        # Step 2: Generate updated code with LLM
        print("🤖 Generating updated code with LLM...")
        code_structure = write_code_update_with_llm(data, current_files)
        
        # Step 3: Prepare files for push
        files = []
        for filename, content in code_structure["files"].items():
            files.append({
                "name": filename,
                "content": content
            })
        
        # Step 4: Push updated files
        print(f"📤 Pushing {len(files)} updated files...")
        latest_sha = push_files_to_repo(repo_name, files, round=2)
        
        # Step 5: Get pages URL

        pages_url = f"https://{gh_user}.github.io/{repo_name}/"
        
        # Step 6: Prepare response
        obj = {
            "email": data.get('email'),
            "task": data.get('task'),
            "round": 2,
            "nonce": data.get('nonce'),
            "repo_url": f"https://github.com/{gh_user}/{repo_name}",
            "commit_sha": latest_sha,
            "pages_url": pages_url,
        }
        
        # Step 7: Hit evaluation URL
        evaluation_url = data.get('evaluation_url')
        if evaluation_url:
            hit_evaluation_url(evaluation_url, obj)
        
        print(f"✅ Round 2 completed successfully!")
        return obj
        
    except Exception as e:
        print(f"❌ ERROR in round_2: {str(e)}")
        raise Exception(f"round_2 failed: {str(e)}")




