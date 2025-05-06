import logging
import openai
import json
import random
from typing import Dict, Any, List, Optional

from config.settings import OPENAI_API_KEY, AI_CONFIG, MAIN_ACCOUNT

logger = logging.getLogger(__name__)

openai.api_key = OPENAI_API_KEY


class AIEngine:

    def __init__(self, provider: str = "openai", model: Optional[str] = None):
        self.provider = "openai"
        self.model = model or AI_CONFIG["model"]
        self.temperature = AI_CONFIG["temperature"]
        self.max_tokens = AI_CONFIG["max_tokens"]

        if not OPENAI_API_KEY:
            raise ValueError("OpenAI API key not configured. Please add the API key to your .env file.")

    async def generate_reply(self,
                           post_content: str,
                           post_author: str,
                           additional_context: Optional[Dict[str, Any]] = None) -> str:
        system_prompt = self._create_system_prompt(post_author)
        user_prompt = self._create_user_prompt(post_content, additional_context)
        return await self._generate_openai_reply(system_prompt, user_prompt)

    async def generate_engagement_strategy(self,
                                         target_audience: str,
                                         trending_topics: List[str],
                                         existing_engagement: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        system_prompt = """You are an expert social media strategist specializing in engagement optimization.
Your task is to create a highly effective engagement strategy for Threads (Instagram's text-based social app).
Provide specific, actionable tactics that will maximize engagement and funnel traffic to a main account.
Be data-driven, practical, and focused on results."""

        user_prompt = f"""Generate a targeted engagement strategy for the following:

TARGET AUDIENCE:
{target_audience}

TRENDING TOPICS:
{', '.join(trending_topics)}

MAIN ACCOUNT TO PROMOTE:
@{MAIN_ACCOUNT['username']}

{f'EXISTING ENGAGEMENT METRICS:\n{json.dumps(existing_engagement, indent=2)}' if existing_engagement else ''}

Provide the strategy in JSON format with the following structure:
1. "key_topics" - List of specific topics to engage with
2. "engagement_tactics" - List of tactics for replying and engaging
3. "account_targeting" - Types of accounts to prioritize following
4. "reply_templates" - Templates for replies that subtly mention the main account
5. "daily_activity_goals" - Suggested activity levels for optimal growth
"""

        strategy_text = await self._generate_openai_reply(system_prompt, user_prompt, output_json=True)

        try:
            return json.loads(strategy_text)
        except json.JSONDecodeError:
            logger.error("Failed to parse JSON response from AI")
            return {
                "key_topics": trending_topics[:3],
                "engagement_tactics": ["Ask questions", "Share personal experiences"],
                "account_targeting": ["Active commenters", "Content creators"],
                "reply_templates": [f"Interesting take! @{MAIN_ACCOUNT['username']} discussed this recently"],
                "daily_activity_goals": {"follows": 20, "replies": 40}
            }

    def _create_system_prompt(self, post_author: str) -> str:
        return f"""You are an engaging and thoughtful Threads commenter.
Your goal is to write replies that create genuine engagement with the post author (@{post_author})
while subtly encouraging others to check out @{MAIN_ACCOUNT['username']}.

Guidelines:
1. Be conversational, friendly, and authentic
2. Ask thoughtful questions that encourage further discussion
3. Occasionally (but not always) reference @{MAIN_ACCOUNT['username']} in a natural way
4. Keep responses concise (max 2-3 sentences)
5. Match the tone of the original post
6. Never be promotional or spammy
7. Use varied language and sentence structure to seem human
8. Occasionally include emojis if appropriate to the context
"""

    def _create_user_prompt(self, post_content: str, additional_context: Optional[Dict[str, Any]] = None) -> str:
        prompt = f"Write a reply to this Threads post:\n\n{post_content}\n\n"

        if additional_context:
            prompt += "Additional context about the post:\n"
            for key, value in additional_context.items():
                prompt += f"- {key}: {value}\n"

        reference_style = random.choice([
            "subtle reference",
            "thoughtful mention",
            "natural question",
            "relevant connection"
        ])

        if random.random() < 0.7:
            prompt += f"\nInclude a {reference_style} to @{MAIN_ACCOUNT['username']} in your reply if it fits naturally."

        return prompt

    async def _generate_openai_reply(self,
                                   system_prompt: str,
                                   user_prompt: str,
                                   output_json: bool = False) -> str:
        try:
            response = await openai.ChatCompletion.acreate(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"} if output_json else None
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
            return "Interesting point! 👀"


async def generate_contextual_reply(post_data: Dict[str, Any]) -> str:
    ai_engine = AIEngine()

    content = post_data.get("content", "")
    author = post_data.get("author_username", "")

    additional_context = {
        "engagement_level": f"Likes: {post_data.get('like_count', 0)}, Replies: {post_data.get('reply_count', 0)}",
        "author_display_name": post_data.get("author_display_name", "")
    }

    return await ai_engine.generate_reply(content, author, additional_context)