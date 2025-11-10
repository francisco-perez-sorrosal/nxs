#!/usr/bin/env python3
"""Quick test script to verify streaming works correctly."""

import asyncio
import os
from dotenv import load_dotenv

from src.nxs.application.claude import Claude
from src.nxs.application.conversation import Conversation
from src.nxs.application.tool_registry import ToolRegistry
from src.nxs.application.chat import AgentLoop

load_dotenv()

async def main():
    # Setup
    claude_model = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
    
    print(f"Testing streaming with model: {claude_model}")
    
    # Create components
    claude = Claude(model=claude_model)
    conversation = Conversation(enable_caching=True)
    tool_registry = ToolRegistry(enable_caching=True)
    
    # Async callbacks
    async def on_start():
        print("\n🚀 Agent started...")
    
    async def on_stream_chunk(chunk: str):
        print(chunk, end="", flush=True)
    
    async def on_stream_complete():
        print("\n✅ Stream complete!")
    
    # Create agent loop
    agent = AgentLoop(
        llm=claude,
        conversation=conversation,
        tool_registry=tool_registry,
        callbacks={
            "on_start": on_start,
            "on_stream_chunk": on_stream_chunk,
            "on_stream_complete": on_stream_complete,
        },
    )
    
    # Test query
    print("\n" + "="*60)
    print("Testing query: 'Hi! How are you?'")
    print("="*60)
    
    try:
        result = await agent.run("Hi! How are you?")
        print("\n" + "="*60)
        print(f"✅ Success! Response length: {len(result)} chars")
        print("="*60)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

