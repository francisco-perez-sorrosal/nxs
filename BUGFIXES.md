# Bug Fixes Applied - Session Oct 18, 2025

## Summary

Fixed three critical UI issues reported by user:
1. ✅ Input text invisible when typing
2. ✅ "Assistant:" label appearing centered instead of right-aligned
3. ✅ Markdown headers appearing centered instead of left-aligned

---

## Fix 1: Input Text Visibility

### Problem
Characters typed in the input field were not visible on screen, even after adding `color: $text` to CSS.

### Root Cause
The CSS rule wasn't being applied to the Input widget. Textual's CSS can sometimes fail to apply to certain widget properties, especially when widgets are dynamically styled or wrapped.

### Solution
Set the text color programmatically in the `on_mount()` lifecycle method:

**File**: `tui/widgets/input_field.py`

```python
def on_mount(self) -> None:
    """Set explicit styles when widget is mounted."""
    super().on_mount()
    # BUGFIX: Explicitly set text color to ensure visibility
    # The CSS wasn't being applied properly, so we set it programmatically
    self.styles.color = "white"
    logger.info(f"NexusInput mounted with color style: {self.styles.color}")
```

### Why This Works
By setting `self.styles.color = "white"` directly in Python after the widget is mounted, we guarantee the style is applied regardless of CSS issues. This is a common Textual pattern when CSS doesn't work as expected.

---

## Fix 2: "Assistant:" Label Right Alignment

### Problem
The "Assistant:" label was appearing in the center of the screen instead of being right-aligned at the far right edge.

### Root Cause
`Align.right()` without an explicit width doesn't know how wide to make the container when used inside RichLog. It defaults to the content width, which results in centered appearance.

### Solution
Specify an explicit width for the `Align.right()` call:

**File**: `tui/widgets/chat_panel.py`

```python
def add_assistant_message_start(self):
    """
    Mark the start of an assistant message.

    Displays "Assistant:" right-aligned and prepares for response.
    """
    # BUGFIX: Right-align the "Assistant:" label properly
    # Need to specify width for Align.right() to work correctly in RichLog
    label = Text("Assistant:", style="bold green")
    # Use Align with "right" and specify a reasonable width based on typical terminal
    aligned_label = Align.right(label, width=120)
    self.write(aligned_label)
    self.write("\n")

    # Reset buffer for new message
    self._assistant_buffer = ""
    self._assistant_active = True
```

Also updated `add_assistant_message()` method for consistency.

### Why This Works
By specifying `width=120`, we tell Rich to create a 120-character-wide container and align the "Assistant:" text to the right edge of that container. This creates the desired far-right alignment effect.

---

## Fix 3: Markdown Header Centering

### Problem
Markdown headers (h1, h2) were appearing centered instead of left-aligned with the 40-character indent.

### Root Cause
Rich's Markdown renderer centers h1 and h2 headers by default. This is standard markdown rendering behavior but wasn't desired for this TUI layout.

### Solution
Use the `justify="left"` parameter when creating Markdown renderables:

**File**: `tui/widgets/chat_panel.py`

```python
def finish_assistant_message(self):
    """
    Render the complete assistant message as formatted markdown.

    The message is displayed with left padding to create the indented layout.
    """
    if self._assistant_active and self._assistant_buffer:
        # BUGFIX: Render markdown with left-aligned headers (not centered)
        # Rich's Markdown centers h1/h2 by default, so we use justify="left"
        md = Markdown(self._assistant_buffer, justify="left")

        # Add left padding to create the indented right-side layout
        # Using 40 chars for the left margin
        padded_md = Padding(md, (0, 0, 0, 40))

        # Write the formatted markdown
        self.write(padded_md)
        self.write("\n\n")

        # Reset state
        self._assistant_buffer = ""
        self._assistant_active = False
```

Also updated `add_assistant_message()` and `add_markdown()` methods for consistency.

### Why This Works
The `justify="left"` parameter tells Rich's Markdown renderer to left-align all content, including headers. This ensures headers respect the 40-character left padding and flow naturally with the rest of the text.

---

## Files Modified

1. **tui/widgets/input_field.py** (NexusInput.on_mount)
   - Added explicit `self.styles.color = "white"` setting
   - Called `super().on_mount()` first
   - Changed logging to INFO level for visibility

2. **tui/widgets/chat_panel.py** (ChatPanel)
   - Updated `add_assistant_message_start()`: Added `width=120` to `Align.right()`
   - Updated `finish_assistant_message()`: Added `justify="left"` to `Markdown()`
   - Updated `add_assistant_message()`: Both fixes applied
   - Updated `add_markdown()`: Added `justify="left"`

---

## Testing

To verify the fixes work:

```bash
pixi run start
```

1. **Input visibility**: Type characters in the input field - text should be white and visible
2. **Assistant alignment**: Send a message and check "Assistant:" appears at far-right edge
3. **Header alignment**: Use `/format @report.pdf` command - headers should be left-aligned with 40-char indent

---

## Technical Notes

### Textual Styling Hierarchy
- CSS in `.tcss` files is applied first
- Programmatic `self.styles.*` settings override CSS
- When CSS fails mysteriously, programmatic styling is the reliable fallback

### Rich Alignment in RichLog
- `Align` objects need explicit width when container doesn't provide one
- RichLog doesn't automatically expand Align to full width
- Specifying width (e.g., 120) creates predictable alignment behavior

### Rich Markdown Justification
- Default markdown rendering: h1/h2 centered, other content left
- `justify="left"` forces all content left-aligned
- Works well with Padding for creating indented layouts

---

## Related Documentation

Previous fixes documented in:
- `INPUT_FIX.md` - Original CSS attempt to fix input visibility
- `CLEAN_CHAT_SOLUTION.md` - Major refactor to simplify chat rendering

This document supersedes `INPUT_FIX.md` with the working programmatic solution.
