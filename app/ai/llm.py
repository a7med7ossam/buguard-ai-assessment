import os

from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

# We use Gemini through its OpenAI-compatible endpoint so we can keep the
# well-supported langchain-openai wrapper. Swap base_url/model/key here to
# move to a different provider without touching the capability modules.
llm = ChatOpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    model="gemini-3.1-flash-lite",
    temperature=0,
)
