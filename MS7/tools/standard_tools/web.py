# MS7/tools/standard_tools/web.py

import os
import json
import requests
from dotenv import load_dotenv

# Load environment variables from the project's .env file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(BASE_DIR, '.env'))

def search_web(query: str) -> str:
    """
    Performs a web search using the Brave Search API and returns a concise
    summary of the top results.

    Args:
        query: The search query.

    Returns:
        A formatted string containing the title, URL, and a snippet for
        each of the top search results, or an error message.
    """
    api_key = os.getenv("BRAVE_SEARCH_API_KEY")
    base_url = "https://api.search.brave.com/res/v1/web/search"
    
    print(f"EXECUTING REAL TOOL: search_web with query='{query}'")

    if not api_key:
        print("ERROR: BRAVE_SEARCH_API_KEY not found in environment.")
        return "Error: The web search service is not configured."

    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key,
    }
    params = {"q": query}

    try:
        response = requests.get(base_url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "web" not in data or "results" not in data["web"]:
            return "No web search results found for that query."

        results = data["web"]["results"]
        if not results:
            return "No web search results found for that query."

        # --- Format the results into a clean, LLM-friendly string ---
        summary = "Here are the top web search results:\n\n"
        for i, result in enumerate(results[:5]): # Return the top 5 results
            summary += f"Result {i+1}:\n"
            summary += f"  Title: {result.get('title', 'N/A')}\n"
            summary += f"  URL: {result.get('url', 'N/A')}\n"
            summary += f"  Snippet: {result.get('description', 'N/A')}\n\n"
        
        return summary

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred while calling Brave API: {http_err}")
        return f"Error: An HTTP error occurred while searching: {response.status_code}"
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return "Error: An unexpected error occurred while performing the web search."