import os
from langchain_openai import ChatOpenAI
from langchain_openai import AzureChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

def get_llm(provider: str, model: str = None):
    if provider == "azure":
        model = model or os.environ.get("AZURE_OPENAI_DEPLOYMENT")
        llm = AzureChatOpenAI(
            azure_deployment=model,
            openai_api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
            azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
            api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
            temperature=0.0,
        )
    elif provider == "openai":
        model = model or os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")
        llm = ChatOpenAI(
            model_name=model,
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )
    elif provider == "google":
        model = model or os.environ.get("GOOGLE_MODEL", "gemini-2.0-flash-lite")
        llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=0.0,
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")
    return llm