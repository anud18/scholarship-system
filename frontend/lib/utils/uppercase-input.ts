/**
 * Input helpers that normalise what the user types.
 */

/**
 * Uppercase an <input>'s value as the user types, keeping the caret in place.
 *
 * Returning `value.toUpperCase()` alone makes React reset the caret to the end
 * whenever a lowercase letter is typed mid-string. Writing the uppercased value
 * back into the DOM first means the state update leaves the DOM unchanged, so
 * the caret stays where the user put it.
 */
export function uppercaseInputValue(input: HTMLInputElement): string {
  const upper = input.value.toUpperCase();
  if (upper !== input.value) {
    const { selectionStart, selectionEnd } = input;
    input.value = upper;
    input.setSelectionRange(selectionStart, selectionEnd);
  }
  return upper;
}
