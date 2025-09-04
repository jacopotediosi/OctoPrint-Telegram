from typing import List


class StringUtils:
    """Static utilities for string manipulation."""

    @staticmethod
    def split_with_escape_handling(param_str: str, separator: str) -> List[str]:
        """
        Split a string by a separator while properly handling escaped characters.

        This function splits a string into parts using the specified separator,
        but treats escaped characters (prefixed with backslash) literally.
        This allows separators to be included in the actual data when escaped.

        Args:
            param_str (str): The string to split
            separator (str): The character to split on

        Returns:
            List[str]: List of split parts with escape sequences processed

        Examples:
            >>> split_with_escape_handling("a,b,c", ',')
            ['a', 'b', 'c']
            >>> split_with_escape_handling("a\\,b,c", ',')  # escaped comma
            ['a,b', 'c']
            >>> split_with_escape_handling("a\\\\,b", ',')  # escaped backslash
            ['a\\', 'b']
        """
        result = []
        current = ""
        escaped = False

        for char in param_str:
            if escaped:
                current += char
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == separator:
                result.append(current)
                current = ""
            else:
                current += char

        result.append(current)
        return result
