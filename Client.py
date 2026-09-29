from dotenv import load_dotenv
from google import genai
import json
import os
from pathlib import Path
from fastmcp import Client
from mcp_client_for_ollama.client import MCPClient as OllamaMCPClient
import asyncio

load_dotenv()


def choose_provider() -> str | None:
    while True:
        try:
            choice = input("Choose model provider (1: Google Gemini, 2: Ollama, or exit): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            return None

        if choice in {"1", "google", "gemini"}:
            return "google"
        if choice in {"2", "ollama"}:
            return "ollama"
        if choice in {"exit", "q", "quit"}:
            return None
        print("Please choose 1 for Google Gemini or 2 for Ollama.")

def read_query() -> str | None:
    try:
        return input("Enter your query: ")
    except (EOFError, KeyboardInterrupt):
        print("\nExiting...")
        return None


def is_greeting(query: str) -> bool:
    return query.strip().lower().rstrip("!,.?") in {
        "hi",
        "hello",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
    }


async def get_feedback_for_query(client: Client, query: str) -> list[dict]:
    resource = await client.read_resource("feedback://get_feedback_list")
    feedback = json.loads(resource[0].text)
    query_lower = query.lower()

    categories = [
        "Application UI",
        "User-friendly",
        "Billing",
        "Rooms",
        "Customer Assistance",
    ]
    sentiments = ["Positive", "Neutral", "Negative"]
    category = next((item for item in categories if item.lower() in query_lower), None)
    sentiment = next((item for item in sentiments if item.lower() in query_lower), None)

    if category:
        result = await client.call_tool(
            "get_feedback_by_category",
            {"data": feedback, "category": category},
        )
        feedback = json.loads(result.content[0].text)

    if sentiment:
        result = await client.call_tool(
            "get_feedback_by_sentiment",
            {"data": feedback, "sentiment": sentiment},
        )
        feedback = json.loads(result.content[0].text)

    return feedback


async def generate_with_google(prompt: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GENAI_API_KEY is not set.")

    gemini_client = genai.Client(api_key=api_key)
    response = await gemini_client.aio.models.generate_content(
        model=os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=500,
            top_p=0.8,
        ),
    )
    return response.text


async def generate_with_ollmcp(prompt: str, client: OllamaMCPClient) -> str:
    response = await client.process_query(prompt)
    if not response:
        raise RuntimeError("Ollama returned an empty response.")
    return response


async def create_ollmcp_client(server_path: Path) -> OllamaMCPClient:
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    ollama_model = os.environ.get("OLLAMA_MODEL", "gemma4:e2b")
    client = OllamaMCPClient(
        model=ollama_model,
        host=ollama_host,
        provider="ollama",
        persist_api_key=False,
    )
    await client.connect_to_servers(server_paths=[str(server_path)])
    return client


async def main():
    server_path = Path(__file__).with_name("Server.py")

    async with Client(server_path) as client:
        provider = choose_provider()
        if provider is None:
            return

        ollama_client = None
        if provider == "ollama":
            ollama_client = await create_ollmcp_client(server_path)

        try:
            query = read_query()

            while query is not None and query.lower() != "exit":
                try:
                    if is_greeting(query):
                        print("Response: Hello! How can I help you analyze the hotel feedback?")
                        query = read_query()
                        continue

                    feedback = await get_feedback_for_query(client, query)
                    question = await client.get_prompt(
                        "get_prompt", {"query": query, "data": feedback}
                    )

                    prompt = question.messages[0].content.text
                    if provider == "google":
                        response_text = await generate_with_google(prompt)
                    else:
                        response_text = await generate_with_ollmcp(prompt, ollama_client)
                    print(f"Response: {response_text}")



                except KeyboardInterrupt:
                    print("\nExiting...")
                    break
                except Exception as e:
                    print(f"Error occurred: {e}")
                query = read_query()
        finally:
            if ollama_client is not None:
                await ollama_client.cleanup()




            
     



if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as error:
        print(f"Error occurred: {error}")

