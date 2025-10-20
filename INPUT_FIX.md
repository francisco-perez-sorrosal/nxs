# Input Field Text Visibility Fix

## Problem

Characters typed in the input field were not visible on screen.

## Root Cause

The CSS styling was setting `background: $surface` but not explicitly setting text `color`, causing the text to potentially be the same color as the background (invisible).

## Solution

Added explicit `color: $text` to the input field styling:

```css
/* Input field */
#input {
    height: 3;
    border: solid $success;
    background: $surface;
    color: $text;  /* ← ADDED: Ensure text is visible */
    padding: 1;
}

/* Also for Input widget directly */
Input {
    color: $text;  /* ← ADDED: Ensure all Input widgets have visible text */
}
```

## Files Modified

- `tui/styles.tcss`: Added `color: $text` to `#input` and `Input` selectors

## Testing

```bash
pixi run start
```

Type in the input field - characters should now be visible!

## Why This Works

Textual's theming system uses CSS variables like `$text` and `$surface`. By explicitly setting `color: $text`, we ensure the input text color contrasts with the background, regardless of the theme.

The `Input` global selector ensures all Input widgets (including the one inside NexusInput) inherit the correct text color.
