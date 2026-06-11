import json
import httpx
import re
from typing import AsyncGenerator, Dict, Any, List, Optional
from openai import OpenAI


class LLMManager:
    """Manages LLM completions for RAG, supporting OpenAI and Google Gemini."""

    @staticmethod
    def build_rag_prompt(question: str, context_chunks: List[Dict[str, Any]]) -> str:
        """Constructs a grounded RAG prompt based on retrieved context chunks."""
        context_str = ""
        for idx, chunk in enumerate(context_chunks):
            meta = chunk["metadata"]
            doc = chunk["document"]
            platform = str(meta.get("platform", "Unknown")).capitalize()
            timestamp = str(meta.get("timestamp", "Unknown Date")).split("T")[0]
            author = str(meta.get("author", "User"))
            
            context_str += f"[Source #{idx + 1}]: {platform} post by {author} on {timestamp}\n"
            context_str += f"Content: {doc}\n"
            context_str += "----------------------------------------\n\n"
            
        prompt = f"""You are an AI assistant helping a user explore a person's social media archive.
Based on the ingested social media posts (from LinkedIn, Twitter, and Instagram) provided in the context below, answer the user's question: "{question}"

Strict Rules:
1. Ground your answer ONLY in the provided context. If the answer cannot be found or directly inferred from the context, respond with: "I cannot find any information about that in the ingested social media data."
2. Proactively cite your sources in the text using bracketed numbers corresponding to the sources, e.g. [1], [2]. At the end of your response, list the sources you cited.
3. Keep the tone helpful, analytical, and objective.
4. Do NOT make up facts, URLs, or extrapolate details that are not in the context.

Context:
----------------------------------------
{context_str or "No relevant social media posts found."}
----------------------------------------

Question: {question}

Answer:"""
        return prompt

    async def generate_stream(
        self, 
        prompt: str, 
        provider: str, 
        api_key: str, 
        model: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Streams completion from OpenAI or Gemini in a highly robust manner."""
        if provider == "openai":
            selected_model = model or "gpt-4o-mini"
            try:
                client = OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model=selected_model,
                    messages=[
                        {"role": "system", "content": "You are a precise, grounded assistant. You only answer based on context."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2,
                    stream=True
                )
                for chunk in response:
                    text = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta.content else ""
                    if text:
                        yield text
            except Exception as e:
                yield f"\n[Error from OpenAI API: {str(e)}]"
                
        elif provider == "groq":
            selected_model = model or "llama-3.3-70b-versatile"
            try:
                client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
                response = client.chat.completions.create(
                    model=selected_model,
                    messages=[
                        {"role": "system", "content": "You are a precise, grounded assistant. You only answer based on context."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2,
                    stream=True
                )
                for chunk in response:
                    text = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta.content else ""
                    if text:
                        yield text
            except Exception as e:
                yield f"\n[Error from Groq API: {str(e)}]"

                
        elif provider == "gemini":
            selected_model = model or "gemini-2.0-flash"
            url = f"https://generativelanguage.googleapis.com/v1/models/{selected_model}:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2}
            }
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    if response.status_code == 200:
                        res_json = response.json()
                        text = res_json["candidates"][0]["content"]["parts"][0]["text"]
                        # Yield in chunks to simulate streaming for a smooth UI transition
                        chunk_size = 30
                        for idx in range(0, len(text), chunk_size):
                            yield text[idx:idx+chunk_size]
                    else:
                        yield f"\n[Error from Gemini (Status {response.status_code}): {response.text}]"
            except Exception as e:
                yield f"\n[Error calling Gemini API: {str(e)}]"

