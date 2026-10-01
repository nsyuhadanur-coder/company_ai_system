import os
import re
from typing import List, Dict, Any, Optional

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


class AIService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model_name = "gemini-3.8-flash"
        self._client = None
        if self.api_key and GENAI_AVAILABLE:
            try:
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"Warning: Failed to initialize Gemini client: {e}")
                self._client = None

    def set_api_key(self, api_key: str):
        """Allows setting or changing the API key at runtime."""
        self.api_key = api_key.strip()
        if self.api_key and GENAI_AVAILABLE:
            try:
                self._client = genai.Client(api_key=self.api_key)
                return True
            except Exception as e:
                print(f"Error setting API key: {e}")
                self._client = None
                return False
        else:
            self._client = None
            return False

    def is_gemini_active(self) -> bool:
        return bool(self._client and self.api_key)

    def generate_response(
        self,
        query: str,
        retrieved_chunks: List[Dict[str, Any]],
        chat_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Generates an HR & Ops grounded response.
        If Gemini is available, uses gemini-3.8-flash.
        Otherwise, falls back to intelligent grounded synthesis.
        """
        # Format citations
        citations = []
        for chunk in retrieved_chunks:
            citations.append({
                "doc_title": chunk["doc_title"],
                "section_title": chunk["section_title"],
                "source_filename": chunk["source_filename"],
                "category": chunk["category"],
                "snippet": chunk["snippet"]
            })

        # Check if we can use Gemini 3.8 Flash
        if self.is_gemini_active():
            try:
                answer = self._generate_with_gemini(query, retrieved_chunks, chat_history)
                return {
                    "answer": answer,
                    "engine": "gemini-3.8-flash",
                    "is_live_gemini": True,
                    "citations": citations
                }
            except Exception as e:
                print(f"Gemini API error, falling back to local synthesis: {e}")
                # Fall through to local synthesis

        # Local intelligent grounded synthesis
        answer = self._generate_local_synthesis(query, retrieved_chunks)
        return {
            "answer": answer,
            "engine": "local-rag-synthesizer",
            "is_live_gemini": False,
            "citations": citations
        }

    def _generate_with_gemini(
        self,
        query: str,
        retrieved_chunks: List[Dict[str, Any]],
        chat_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        # Construct grounded context
        context_parts = []
        for i, chunk in enumerate(retrieved_chunks):
            context_parts.append(
                f"[Document: {chunk['doc_title']} | Section: {chunk['section_title']} | Source: {chunk['source_filename']}]\n"
                f"{chunk['content']}\n"
            )
        context_str = "\n---\n".join(context_parts)

        system_instruction = (
            "You are Astra, the intelligent corporate AI Assistant for HR & Internal Operations. "
            "Your objective is to provide authoritative, helpful, clear, and empathetic answers to company employees.\n\n"
            "CRITICAL GUIDELINES:\n"
            "1. Ground your answer strictly in the provided company policy excerpts. "
            "Do not invent policies or speculate beyond the provided documentation.\n"
            "2. Always cite specific policies, section numbers, and guidelines in your response "
            "(e.g., 'According to HR-POL-001 Section 2.1...').\n"
            "3. Use structured formatting with bold headings, bullet points, and numbered steps where appropriate.\n"
            "4. If a procedure requires taking an action (such as booking PTO, filing an expense, requesting hardware, or logging a grievance), "
            "clearly outline the required steps, deadlines, and portals.\n"
            "5. If the provided excerpts do not contain enough information to answer definitively, state that clearly "
            "and direct the employee to file an HR Helpdesk Ticket or contact their HRBP."
        )

        prompt = f"""COMPANY POLICY CONTEXT:
{context_str}

EMPLOYEE INQUIRY:
{query}

Please formulate a comprehensive, clear, and grounded answer for the employee:"""

        # Call Gemini 3.8 Flash
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
            )
        )
        return response.text

    def _generate_local_synthesis(
        self,
        query: str,
        retrieved_chunks: List[Dict[str, Any]]
    ) -> str:
        """Intelligent grounded answer synthesis from top retrieved chunks."""
        if not retrieved_chunks:
            return (
                "I couldn't locate specific company policies matching your inquiry in the current "
                "HR & Internal Operations Knowledge Base.\n\n"
                "**Recommended Next Steps:**\n"
                "- Check the **Policies Hub** tab to browse complete manuals.\n"
                "- Submit an inquiry via the **HR/IT Helpdesk** tab for personalized support from a People Partner or IT Specialist."
            )

        top_chunk = retrieved_chunks[0]
        secondary_chunks = retrieved_chunks[1:]

        # Clean content and extract key points
        lines = top_chunk["content"].split("\n")
        cleaned_body = []
        for line in lines:
            line_str = line.strip()
            if not line_str.startswith("#") and not line_str.startswith("**Document ID:") and not line_str.startswith("**Effective Date:"):
                cleaned_body.append(line_str)
        
        body_text = "\n".join([l for l in cleaned_body if l])

        # Compose high-fidelity response
        parts = [
            f"Based on the official **{top_chunk['doc_title']}** (*Section: {top_chunk['section_title']}*):\n",
            body_text,
            "\n"
        ]

        # Add secondary relevant context if high relevance
        if secondary_chunks and secondary_chunks[0].get("relevance_score", 0) > 1.2:
            sec_chunk = secondary_chunks[0]
            parts.append(f"\n### Additional Related Policy: {sec_chunk['section_title']}")
            parts.append(f"*(From {sec_chunk['doc_title']})*\n")
            sec_lines = [l.strip() for l in sec_chunk["content"].split("\n") if l.strip() and not l.startswith("#")]
            parts.append("\n".join(sec_lines[:5]))

        # Practical next action callout
        parts.append("\n\n---")
        parts.append(
            "💡 **Need further assistance?** You can submit a formal request via the "
            "**Employee Self-Service** tools or file an inquiry in the **Helpdesk Desk**."
        )

        return "\n".join(parts)
