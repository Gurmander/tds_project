import os
import time 
from dotenv import load_dotenv
import requests
import base64
import json

load_dotenv()

# os.getenv() for sec
secret_key = os.getenv('MY_SECRET')
api_token = os.getenv('API_TOKEN')
gh_token = os.getenv('GITHUB_TOKEN')
gh_user = os.getenv('GITHUB_USERNAME')



def verify_secret(test):
    return test == secret_key


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


def enable_github_pages_0(repo_name: str):
    # enable github pages for given repo
    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json"
    }

    payload = {
        "build_type": "legacy",
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
    if response.status_code != 201:
        raise Exception(f"Failed to enable github pages: {response.status_code}: {response.text}")
    else:
        return response.text



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





# sha required if want to update file, in round 2
def get_sha_of_latest_commit(repo_name: str, branch: str = "main") -> str:
    response = requests.get(f"https://api.github.com/repos/{gh_user}/{repo_name}/commits/{branch}")
    if response.status_code != 200:
        raise Exception("Failed to get latest commit sha: {response.status_code}, {response.text}")
    return response.json().get("sha")



def handle_query(data):

    repo_name = f"{data['task'].replace(' ', '-')}-{data['nonce']}"
    try:
        if data.get('round') ==1:
            # test_api_connection()
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

        else:
            # latest_sha = get_sha_of_latest_commit(repo_name)
            handle_round_2(data)            

        

    except Exception as e:
        print(f"❌ ERROR in round_1: {str(e)}")
        print(f"🧹 Cleaning up - attempting to delete repo: {repo_name}")
        
        # Attempt cleanup
        delete_github_repo(repo_name)
        
        # Re-raise the exception so caller knows it failed
        raise Exception(f"round_1 failed: {str(e)}")        



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




def call_aipipe_llm(prompt: str, model: str = "gpt-4o-mini") -> str:
    """
    Call aipipe API with a prompt and return the response.
    
    Args:
        prompt: The prompt to send to the LLM
        model: Model to use
               Other options: "openai/gpt-4.1-nano", "openai/gpt-4o", etc.
    
    Returns:
        The LLM's response text
    """
    
    url = "https://aipipe.org/openrouter/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
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


def write_code_with_llm(task_data: dict) -> dict:
    """
    Use LLM to generate code based on task requirements
    Returns dict with files and their contents
    """
    
    # Extract task information
    task_id = task_data.get('task', 'unknown-task')
    brief = task_data.get('brief', '')
    checks = task_data.get('checks', [])
    attachments = task_data.get('attachments', [])
    
    # Format checks
    checks_formatted = "\n".join([f"{i+1}. {check}" for i, check in enumerate(checks)])
    
    # Format attachments info
    attachments_info = ""
    if attachments:
        attachments_info = "ATTACHMENTS PROVIDED:\n"
        for att in attachments:
            name = att.get('name', 'file')
            url_preview = att.get('url', '')[:80] + '...' if len(att.get('url', '')) > 80 else att.get('url', '')
            attachments_info += f"- {name}: {url_preview}\n"
    
    # OPTIMIZED PROMPT - Clear, concise, forces JSON output
    prompt = f"""Generate a complete, working web application for GitHub Pages deployment.

TASK: {task_id}
DESCRIPTION: {brief}

REQUIREMENTS (ALL must be met):
{checks_formatted}

{attachments_info}

DEPLOYMENT CONSTRAINTS:
• Static site only (GitHub Pages) - NO backend servers
• index.html must be at root directory
• Use client-side JavaScript only (vanilla JS or CDN libraries)
• No Node.js, no API endpoints, no server-side code
• All processing happens in the browser

SECURITY:
• NO API keys, secrets, or tokens in code
• Use environment variables if needed (document in README)

FILE REQUIREMENTS:
1. index.html - Complete working app at root (not in subfolder)
2. Additional .js/.css files if needed (or use inline/CDN)
3. README.md - Professional, with:
   - Project summary
   - How to use (open index.html or GitHub Pages URL)
   - How to pass URL parameters (?url=...)
   - MIT License included
4. .gitignore - Basic ignore file

CODE QUALITY:
• Write COMPLETE, FUNCTIONAL code (no TODOs or placeholders)
• Keep code concise (under 200 lines per file)
• Use short variable names (i, el, btn, img, etc.)
• Minimal comments (only where essential)
• Handle errors gracefully

URL PARAMETERS:
If the task requires reading URLs from query params:
const url = new URLSearchParams(window.location.search).get('url') || 'default-or-sample-url';

ATTACHMENTS:
If attachments are provided, embed them as:
• Default sample data (base64 data URI)
• OR load from ?url=... parameter when provided

OUTPUT FORMAT (CRITICAL - PURE JSON ONLY):
Return ONLY this JSON structure with no markdown, no code blocks, no explanations:

{{
  "files": {{
    "index.html": "<!DOCTYPE html>\\n<html lang=\\"en\\">\\n<head>...</head>\\n<body>...</body>\\n</html>",
    "README.md": "# Project Title\\n\\n## Summary\\n...\\n## License\\nMIT License...",
    ".gitignore": "node_modules/\\n.env\\n.DS_Store",
    "style.css": "body {{ margin: 0; }}",
    "script.js": "// JavaScript code"
  }},
  "main_language": "javascript",
  "description": "Brief one-line description"
}}

EXAMPLE MINIMAL index.html:
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

Generate the complete application now (JSON only):"""

    try:
        print(f"📝 Prompt length: {len(prompt)} characters")
        
        # Call LLM API
        print("🤖 Calling LLM...")
        response_text = call_aipipe_llm(prompt=prompt)
        
        print(f"📊 Response length: {len(response_text)} characters")
        print(f"📋 Response preview (first 100): {response_text[:100]}")
        print(f"📋 Response preview (last 100): {response_text[-100:]}")
        
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
        
        if not code_structure["files"]:
            raise ValueError("'files' dictionary is empty")
        
        # Ensure index.html exists
        if "index.html" not in code_structure["files"]:
            raise ValueError("Missing required 'index.html' file")
        
        # Ensure README.md exists and has MIT license
        if "README.md" not in code_structure["files"]:
            code_structure["files"]["README.md"] = generate_default_readme(task_id, brief)
        else:
            readme = code_structure["files"]["README.md"]
            if "MIT License" not in readme and "MIT" not in readme:
                readme += "\n\n## License\n\nMIT License\n\nCopyright (c) 2025\n\nPermission is hereby granted, free of charge, to any person obtaining a copy of this software..."
                code_structure["files"]["README.md"] = readme
        
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
        
        # Save problematic response
        with open('failed_llm_response.txt', 'w', encoding='utf-8') as f:
            f.write(response_text)
        print("💾 Saved full response to 'failed_llm_response.txt'")
        
        raise Exception(f"Error parsing LLM JSON response: {str(e)}")
        
    except Exception as e:
        print(f"❌ Error generating code: {e}")
        raise Exception(f"Error generating code with LLM: {str(e)}")




# GENERATE LLM CODE
def write_code_with_llm_0(task_data: dict) -> dict:
    """
    Use Claude to generate code based on task requirements
    Returns dict with files and their contents
    """
    
    # Extract task information
    task_id = task_data.get('task', 'unknown-task')
    brief = task_data.get('brief', '')
    checks = task_data.get('checks', [])
    attachments = task_data.get('attachments', [])
    
    # Format checks for the prompt
    checks_formatted = "\n".join([f"- {check}" for check in checks])
    
    # Format attachments info
    attachments_info = ""
    if attachments:
        attachments_info = "\n\nAttachments provided:\n"
        for att in attachments:
            attachments_info += f"- {att['name']} (data URI provided)\n"
    
    prompt = f"""You are an expert full-stack developer. Generate a COMPLETE, PRODUCTION-READY minimal application based on these requirements:

    TASK: {task_id}
    BRIEF: {brief}

    EVALUATION CRITERIA (must meet ALL of these):
    {checks_formatted}

    {attachments_info}

    CRITICAL SECURITY REQUIREMENTS:
    1. NEVER include any secrets, API keys, passwords, or tokens in the code
    2. Use environment variables for ALL sensitive data
    3. Include a .env.example file with placeholder values
    4. Add a comprehensive .gitignore to prevent secrets from being committed
    5. Document all required environment variables in README.md
    6. Index.html file must be at root, not inside another folder.

    REQUIRED FILES:
    1. Complete application code (fully functional, not pseudo-code)
    2. README.md with:
    - Project summary and purpose
    - Prerequisites and setup instructions
    - Environment variables needed
    - Step-by-step usage guide
    - Code structure explanation
    - MIT License section
    3. .gitignore (comprehensive)
    4. .env.example (all required env vars with placeholders)
    5. requirements.txt or package.json (depending on stack)
    6. Any configuration files needed

    WORKING WITH ATTACHMENTS:
    - If attachments are provided (like {attachments_info}), they should be:
    * Embedded as base64 data URLs for default/sample data
    * OR loaded from the ?url=... query parameter when provided
    - Example: const url = new URLSearchParams(window.location.search).get('url') || 'data:image/png;base64,...'    

    README STRUCTURE (must be professional and complete):
    ```markdown
    # Project Name

    ## Summary
    Brief description of what this application does.

    ## Prerequisites
    List all requirements (Python 3.x, Node.js, etc.)

    ## Setup Instructions
    1. Clone repository
    2. Install dependencies
    3. Configure environment variables
    4. Run the application

    ## Environment Variables
    Document all required environment variables with descriptions.

    ## Usage
    Clear instructions on how to use the application.

    ## Code Structure
    Explain the project structure and key components.

    ## License
    MIT License - see below for full text.
    ```

    FORMAT YOUR RESPONSE AS JSON:
    {{
        "files": {{
            "filename.ext": "complete file content here",
            "folder/file.ext": "complete file content here",
            "README.md": "complete professional README",
            ".gitignore": "comprehensive gitignore",
            ".env.example": "env template"
        }},
        "main_language": "python|javascript|etc",
        "description": "Brief description",
        "env_vars_needed": ["VAR1", "VAR2"]
    }}

    IMPORTANT:
    - Write COMPLETE, WORKING code (not TODO comments or placeholders)
    - Handle all edge cases
    - Include proper error handling
    - Add helpful code comments
    - Ensure code is secure and follows best practices
    - Make sure all evaluation criteria are met
    """

    prompt1 = f"""You are an expert full-stack developer. Generate a COMPLETE, PRODUCTION-READY application based on these requirements:

        TASK: {task_id}
        BRIEF: {brief}

        EVALUATION CRITERIA (must meet ALL of these):
        {checks_formatted}

        {attachments_info}

        CRITICAL DEPLOYMENT REQUIREMENTS:
        1. This will be deployed on GitHub Pages (STATIC HOSTING ONLY)
        2. NO backend server code - everything must run in the browser
        3. NO API endpoints like /solve, /api/*, etc. - use client-side JavaScript or other language, as required
        4. Use only client-side libraries and browser APIs
        5. If external APIs are needed, they must be CORS-enabled public APIs
        6. All processing must happen in the browser using language like JavaScript, Python etc.

        CRITICAL SECURITY REQUIREMENTS:
        1. NEVER include any secrets, API keys, passwords, or tokens in the code
        2. Use environment variables for ALL sensitive data
        3. Include a .env.example file with placeholder values (if backend is needed later)
        4. Add a comprehensive .gitignore to prevent secrets from being committed
        5. Document all required environment variables in README.md

        FILE STRUCTURE REQUIREMENTS:
        1. index.html MUST be at the root directory (not in any subfolder)
        2. Keep all HTML, CSS, and JavaScript files at the root or in simple folders like /css, /js
        3. Use relative paths for all resources

        TECHNICAL CONSTRAINTS:
        1. Use vanilla JavaScript or CDN-hosted libraries only (no npm packages that need building)
        2. All JavaScript must run in the browser - no Node.js server code
        3. For any data processing, use client-side libraries from CDN etc. (like TensorFlow.js, etc.)
        4. If you need to process images, use Canvas API or FileReader API.
        5. URL parameters should be read using: new URLSearchParams(window.location.search)

        WORKING WITH ATTACHMENTS:
        - If attachments are provided (like {attachments_info}), they should be:
        * Embedded as base64 data URLs for default/sample data
        * OR loaded from the ?url=... query parameter when provided
        - Example: const url = new URLSearchParams(window.location.search).get('url') || 'data:image/png;base64,...'

        REQUIRED FILES:
        1. index.html - Complete, working frontend application at ROOT
        2. Any additional .js or .css files if needed (use CDN links when possible)
        3. README.md with:
        - Project summary and purpose
        - How it works (client-side architecture)
        - Prerequisites (just a modern browser)
        - Usage instructions (open index.html or visit GitHub Pages URL)
        - How to pass parameters via URL (?url=...)
        - MIT License section
        4. .gitignore (basic, for any future development files)

        README STRUCTURE (must be professional and complete):
        ```markdown
        # Project Name

        ## Summary
        Brief description of what this application does.

        ## How It Works
        Explain that this is a client-side application that runs entirely in the browser.

        ## Prerequisites
        - Modern web browser (Chrome, Firefox, Safari, Edge)
        - Internet connection (if using CDN libraries)

        ## Usage
        1. Open the GitHub Pages URL: https://[username].github.io/[repo-name]/
        2. Pass parameters via URL if needed: ?url=https://example.com/image.png
        3. The application will process everything in your browser

        ## Technical Details
        - Pure client-side JavaScript
        - No backend server required
        - Runs on GitHub Pages
        - Uses [list any CDN libraries]

        ## Code Structure
        Explain the project structure and key components.

        ## License
        MIT License
        """    


    try:
        # Call aipipe API
        response_text = call_aipipe_llm(
            prompt=prompt,
            # model="anthropic/claude-sonnet-4-20250514"  # or "openai/gpt-4o"
        )
        
        
        # Parse JSON from response (robust extraction), llm returns files in json format, capturing the files here
        code_structure = extract_json_from_response(response_text)
        
        # Ensure MIT license is in README if not present
        if "README.md" in code_structure["files"]:
            readme_content = code_structure["files"]["README.md"]
        
        # Ensure .gitignore exists
        if ".gitignore" not in code_structure["files"]:
            code_structure["files"][".gitignore"] = get_default_gitignore()
        
        
        print("CODE GENERATED SUCCESSFULLY:::: ")
        return code_structure
        
    except Exception as e:
        raise Exception(f"Error generating code with LLM: {str(e)}")
    

# TODO NOT READY YET
def write_code_update_with_llm(task_data: dict, current_files: dict) -> dict:
    """
    Use LLM to update existing code based on new requirements
    """
    task_id = task_data.get('task', 'unknown-task')
    brief = task_data.get('brief', '')
    checks = task_data.get('checks', [])
    attachments = task_data.get('attachments', [])
    round_2 = task_data.get('round2', [])
    
    checks_formatted = "\n".join([f"- {check}" for check in checks])
    
   # Format current files with smart truncation
    current_files_formatted = []
    for filename, content in current_files.items():
        if len(content) > 1000:
            preview = f"{content[:500]}\n\n... [truncated {len(content) - 1000} chars] ...\n\n{content[-500:]}"
            current_files_formatted.append(f"=== {filename} ===\n{preview}")
        else:
            current_files_formatted.append(f"=== {filename} ===\n{content}")
    
    current_files_str = "\n\n".join(current_files_formatted)
    
    # Format attachments information
    attachments_info = ""
    if attachments:
        attachments_list = []
        for att in attachments:
            name = att.get('name', 'unknown')
            url = att.get('url', '')
            url_preview = url[:50] + '...' if len(url) > 50 else url
            attachments_list.append(f"  - {name}: {url_preview}")
        attachments_info = "Available attachments:\n" + "\n".join(attachments_list)

    
    prompt1 = f"""You are an expert full-stack developer. You need to UPDATE an existing application based on new requirements and feedback.

TASK: {task_id}
ROUND: 2 (Update existing code)

CURRENT APPLICATION FILES:
{current_files_formatted}

NEW REQUIREMENTS/FEEDBACK:
{brief}


EVALUATION CRITERIA (must meet ALL of these):
{checks_formatted}

CRITICAL SECURITY REQUIREMENTS:
1. NEVER include any secrets, API keys, passwords, or tokens in the code
2. Use environment variables for ALL sensitive data
3. Include a .env.example file with placeholder values
5. Update all required environment variables in README.md
6. Index.html file must be at root, not inside another folder.

YOUR TASK:
1. Analyze the current code
2. Identify what needs to be updated based on the feedback/requirements
3. Generate COMPLETE updated files (not just diffs - full file content)
4. Ensure all evaluation criteria are met
5. Maintain the same architecture
6. Keep the professional README structure and update it.

WORKING WITH ATTACHMENTS:
- If attachments are provided (like {attachments_info}), they should be:
* Embedded as base64 data URLs for default/sample data
* OR loaded from the ?url=... query parameter when provided
- Example: const url = new URLSearchParams(window.location.search).get('url') || 'data:image/png;base64,...'    


IMPORTANT RULES:
- Return ALL files (even unchanged ones) with complete content
- Do NOT use placeholders or TODO comments
- Make the code production-ready
- Test logic should work correctly
- Fix any bugs from Round 1

Round 2 details to comply with: 
{round_2}


FORMAT YOUR RESPONSE AS JSON:
{{
    "files": {{
        "index.html": "complete updated HTML file",
        "README.md": "complete updated README",
        "script.js": "complete updated JavaScript if separate",
        ".gitignore": "gitignore content",
        ... all other files ...
    }},
    "main_language": "javascript",
    "description": "Brief description of changes made",
    "changes_summary": "Summary of what was updated and why"
}}

Remember: Return COMPLETE file contents, not just the changed parts!
"""


    prompt = f"""You are an expert full-stack developer updating an existing application based on new requirements.

TASK ID: {task_id}
ROUND: 2 (Update existing code)

CURRENT APPLICATION FILES:
{current_files_str}

NEW REQUIREMENTS:
{brief}

{attachments_info}

EVALUATION CRITERIA (ALL must pass):
{checks_formatted}

ROUND 2 DETAILS: Comply with given instructions:
{round_2}

CRITICAL REQUIREMENTS:

1. SECURITY:
   - NEVER include secrets, API keys, passwords, or tokens in code
   - Use environment variables for ALL sensitive data
   - Include .env.example with placeholder values
   - Document all required environment variables in README.md

2. FILE STRUCTURE:
   - index.html MUST be at repository root (not in subdirectories)
   - Maintain consistent project structure

3. ATTACHMENT HANDLING:
   - If attachments are provided, handle them flexibly:
     * For default/sample data: embed as base64 data URLs
     * Support loading from URL query parameter: ?url=...
     * Example pattern:
       ```javascript
       const dataUrl = new URLSearchParams(window.location.search).get('url') 
                    || 'data:text/csv;base64,<embedded_data>';
       ```
   - Parse attachment URLs correctly (they may contain template variables like ${{seed}})

4. CODE QUALITY:
   - Return COMPLETE file contents (not diffs or partial updates)
   - NO placeholders or TODO comments
   - Production-ready, tested code
   - Fix ALL bugs from previous rounds
   - Ensure all evaluation criteria pass

5. DOCUMENTATION:
   - Keep README.md professional and comprehensive
   - Update all sections affected by changes
   - Document new features and requirements

YOUR TASK:
1. Analyze current code thoroughly
2. Identify required updates based on feedback/requirements
3. Generate COMPLETE updated files with full content
4. Verify all evaluation criteria will pass
5. Maintain architectural consistency
6. Ensure professional quality

RESPONSE FORMAT (valid JSON only):
{{
    "files": {{
        "index.html": "complete updated HTML content",
        "README.md": "complete updated README content",
        "script.js": "complete JavaScript if separate file",
        ".gitignore": "standard gitignore content",
        ".env.example": "example environment variables if needed"
    }},
    "main_language": "javascript",
    "description": "Concise description of changes made",
    "changes_summary": "Detailed summary of updates and rationale"
}}

IMPORTANT: Return the raw JSON object only, with COMPLETE file contents. Do not use markdown code blocks or any wrapper text."""


    try:
        response_text = call_aipipe_llm(
            prompt=prompt,
            # model="anthropic/claude-sonnet-4-20250514"
        )
        
        code_structure = extract_json_from_response(response_text)
        
        print(f"✅ CODE UPDATED SUCCESSFULLY")
        if "changes_summary" in code_structure:
            print(f"📝 Changes: {code_structure['changes_summary']}")
        
        return code_structure
        
    except Exception as e:
        raise Exception(f"Error updating code with LLM: {str(e)}")


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





def test_api_connection():
    prompt = "Give 2+2"
    response = call_aipipe_llm(prompt)

    print("#"*60)
    print(response)
    print("#"*60)



