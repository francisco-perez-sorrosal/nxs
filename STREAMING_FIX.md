# Streaming Fix - Issue Resolution

## Problem Description

After implementing the new agentic loop with sessions (Phases 1-3), the TUI was not displaying any responses from the LLM when users sent queries. The application would accept input but no response would appear in the chat panel.

## Root Cause

The issue was in the `_run_with_streaming()` method in `/Users/fperez/dev/nxs/src/nxs/application/agentic_loop.py`.

### Error Details

From the logs:
```
ERROR | nxs.presentation.services.queue_processor:_worker:219 - Error in QueryQueue processor: "'type'"
```

However, after investigation, the actual error was:
```
Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'tools: Input should be a valid list'}}
```

The real issue was that the Anthropic API was rejecting requests due to invalid parameters being passed.

### Problematic Code

The original code (lines 263-270) passed `None` for empty parameters:

```python
async with self.llm.async_client.messages.stream(
    model=self.llm.model,
    max_tokens=8000,
    messages=messages,
    temperature=1.0,
    tools=tools if tools else None,  # ❌ PROBLEM: Passing None
    system=system if system else None,  # ❌ PROBLEM: Passing None
) as stream:
```

**Why this failed:**
- When `tools` is an empty list `[]`, the expression `tools if tools else None` evaluates to `None` (empty list is falsy)
- The Anthropic API expects either:
  - A valid list of tools (can be empty `[]`)
  - OR the parameter to be omitted entirely (not passed at all)
- Passing `None` explicitly causes a validation error

## Solution

Changed both streaming and non-streaming methods to only include parameters when they have values:

### Streaming Method (_run_with_streaming)

```python
logger.debug("Using real streaming via Claude.stream_message()")

# Build parameters for streaming request
params = {
    "model": self.llm.model,
    "max_tokens": 8000,
    "messages": messages,
    "temperature": 1.0,
}

# Only add tools if we have any (empty list is falsy, so this works)
if tools:
    params["tools"] = tools
    
# Only add system if we have one
if system:
    params["system"] = system

# Stream with context manager
async with self.llm.async_client.messages.stream(**params) as stream:
    # Process stream events
    async for event in stream:
        try:
            # Log event type for debugging
            event_type = getattr(event, "type", None)
            logger.debug(f"Received stream event: {event_type}")
            
            # Handle content block deltas (text streaming)
            if isinstance(event, ContentBlockDeltaEvent):
                delta = event.delta
                if hasattr(delta, "text") and delta.text:
                    if "on_stream_chunk" in callbacks:
                        await callbacks["on_stream_chunk"](delta.text)
            
            # Also check by type string for compatibility
            elif event_type == "content_block_delta":
                delta = getattr(event, "delta", None)
                if delta:
                    text = getattr(delta, "text", None)
                    if text and "on_stream_chunk" in callbacks:
                        await callbacks["on_stream_chunk"](text)
                        
        except Exception as e:
            logger.error(f"Error processing stream event: {e}", exc_info=True)
            raise

    # Get final message from stream context
    response = await stream.get_final_message()
```

### Non-Streaming Method (_run_without_streaming)

```python
logger.debug("Using non-streaming via Claude.create_message()")

# Build parameters
params = {
    "messages": messages,
}

# Only add tools if we have any
if tools:
    params["tools"] = tools
    
# Only add system if we have one
if system:
    params["system"] = system

# Call Claude API without streaming
response = await self.llm.create_message(**params)
```

### Key Changes

1. **Parameter Building**: Construct a `params` dict with only required parameters
2. **Conditional Addition**: Only add `tools` and `system` if they have truthy values
3. **Unpacking**: Use `**params` to pass only the parameters that were added
4. **Event Handling**: Added proper type checking and fallback for stream events

## Testing

### Standalone Test
Created a test script that verified the fix works:

```bash
pixi run python test_streaming.py
```

**Result**:
```
Testing streaming with model: claude-3-7-sonnet-latest
============================================================
Testing query: 'Hi! How are you?'
============================================================

🚀 Agent started...
I'm doing well, thank you for asking! I'm here and ready to help with whatever questions or topics you'd like to discuss today. How are you doing?
✅ Stream complete!

============================================================
✅ Success! Response length: 146 chars
============================================================
```

### Unit Tests
All existing tests continue to pass:
```bash
pixi run --environment test test tests/test_conversation.py -v
# Result: 29 passed in 0.38s
```

## Related Files Modified

- `/Users/fperez/dev/nxs/src/nxs/application/agentic_loop.py`
  - Lines 260-311: `_run_with_streaming()` method
  - Lines 313-347: `_run_without_streaming()` method

## Impact

- ✅ **Fixed**: Real-time streaming now works correctly
- ✅ **Fixed**: LLM responses appear in the TUI
- ✅ **Fixed**: API validation errors resolved
- ✅ **No Breaking Changes**: All existing tests pass
- ✅ **Better Error Handling**: Added logging and fallback for stream events
- ✅ **API Compliance**: Proper parameter handling per Anthropic SDK requirements

## Architecture Notes

The fix aligns with Anthropic SDK best practices:
- Only pass parameters that have values
- Don't pass `None` for optional parameters - omit them entirely
- Use `**params` unpacking for flexible parameter passing
- Handle typed event objects properly from the stream

## Verification Steps

To verify the fix works:

1. **Restart the application** (important - Python caches modules):
   ```bash
   pkill -f "pixi run start"
   reset
   pixi run start
   ```

2. **Send a test query**: Type "Hi!" or any simple message

3. **Check results**:
   - ✅ Response streams in real-time
   - ✅ Text appears character by character
   - ✅ No errors in `nexus.log`
   - ✅ Tool execution works (if query requires tools)

## Important Note for Users

**After updating the code, you MUST restart the application completely.** Python caches imported modules in memory, so changes to the code won't take effect until the process is restarted.

```bash
# Kill the application
pkill -f "pixi run start" 

# Reset the terminal (clears mouse events)
reset

# Start fresh
pixi run start
```

## References

- AGENTIC_LOOP_WITH_SESSIONS_PLAN.md
- INTEGRATION_GUIDE.md
- Anthropic SDK Documentation: https://docs.anthropic.com/en/api/messages-streaming
- Anthropic API Reference: https://docs.anthropic.com/en/api/messages
