"""
Search Manager - Text-based message searching (exact and regex modes)
"""
import logging
import os
import re
import unicodedata
from collections import defaultdict
from typing import Optional

import yaml

from src.mcp_core.engine.provider_loader import get_provider_config_value

# Provider name
PROVIDER_NAME = "google_chat"

# Get configuration values
SEARCH_CONFIG_YAML_PATH = get_provider_config_value(
    PROVIDER_NAME,
    "search_config_path"
)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("search_manager")


class SearchManager:
    """Manages search operations using exact and regex matching."""

    def __init__(self, config_path: str = ("%s" % SEARCH_CONFIG_YAML_PATH)):
        """Initialize the search manager with the provided configuration file."""
        logger.info(f"Initializing SearchManager with config: {config_path}")
        self.config = self._load_config(config_path)
        self.search_modes = {}
        self._initialize_search_modes()

    def _load_config(self, config_path: str) -> dict:
        """Load search configuration from a YAML file."""
        if not os.path.exists(config_path):
            logger.error(f"Search configuration file not found: {config_path}")
            raise FileNotFoundError(f"Search configuration file not found: {config_path}")

        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        logger.info(f"Loaded configuration with {len(config.get('search_modes', []))} search modes")
        return config

    def _initialize_search_modes(self):
        """Initialize the enabled search modes based on configuration."""
        for mode in self.config.get('search_modes', []):
            if mode.get('enabled', False):
                # Skip semantic mode - not supported in this lightweight version
                if mode['name'] == 'semantic':
                    logger.info(f"Skipping semantic mode (not available in lightweight version)")
                    continue
                self.search_modes[mode['name']] = mode
                logger.info(f"Enabled search mode: {mode['name']}")

    def get_default_mode(self) -> str:
        """Get the default search mode from configuration."""
        default = self.config.get('search', {}).get('default_mode', 'exact')
        # Fall back to exact if semantic was default
        if default == 'semantic':
            default = 'exact'
        logger.info(f"Using default search mode: {default}")
        return default

    def search(self, query: str, messages: list[dict], mode: Optional[str] = None) -> list[tuple[float, dict]]:
        """
        Search messages using the specified mode.

        Args:
            query: The search query
            messages: list of message objects to search through
            mode: Search mode (exact, regex, hybrid)
                  If None, uses the default mode from config

        Returns:
            list of tuples (score, message) sorted by relevance score (descending)
        """
        logger.info(f"Starting search with query: '{query}', mode: {mode or 'default'}, message count: {len(messages)}")

        if mode is None:
            mode = self.get_default_mode()
            logger.info(f"Using default mode: {mode}")

        # Semantic mode not supported - fall back to exact
        if mode == "semantic":
            logger.warning("Semantic search not available in lightweight version, using exact search")
            mode = "exact"

        # Verify mode exists in config
        if mode != "hybrid" and mode not in self.search_modes:
            logger.error(f"Search mode '{mode}' not found in configuration or not enabled")
            return self._exact_search(query, messages)

        if mode == "hybrid":
            logger.info("Using hybrid search mode (exact + regex)")
            return self._hybrid_search(query, messages)
        elif mode == "exact":
            logger.info("Using exact search mode")
            return self._exact_search(query, messages)
        elif mode == "regex":
            logger.info("Using regex search mode")
            return self._regex_search(query, messages)
        else:
            logger.error(f"Unknown search mode: {mode}")
            raise ValueError(f"Unknown search mode: {mode}")

    def _exact_search(self, query: str, messages: list[dict]) -> list[tuple[float, dict]]:
        """Perform exact (case-insensitive substring) matching."""
        results = []
        # Normalize the query to handle Unicode characters like smart quotes
        normalized_query = unicodedata.normalize('NFKD', query)
        # Explicitly replace smart apostrophes with standard ASCII apostrophes
        normalized_query = normalized_query.replace('\u2019', "'").replace('\u2018', "'")
        query_lower = normalized_query.lower()
        weight = self.search_modes.get("exact", {}).get("weight", 1.0)

        logger.info(f"Exact search normalized query: '{query}' -> '{normalized_query}' -> '{query_lower}'")

        # Define contraction mappings (both directions)
        contraction_pairs = {
            "don't": ["didn't", "do not", "did not"],
            "didn't": ["don't", "did not", "do not"],
            "isn't": ["wasn't", "is not", "was not"],
            "wasn't": ["isn't", "was not", "is not"],
            "can't": ["couldn't", "cannot", "could not"],
            "couldn't": ["can't", "could not", "cannot"],
            "won't": ["wouldn't", "will not", "would not"],
            "wouldn't": ["won't", "would not", "will not"],
            "aren't": ["weren't", "are not", "were not"],
            "weren't": ["aren't", "were not", "are not"],
            "haven't": ["hadn't", "have not", "had not"],
            "hadn't": ["haven't", "had not", "have not"]
        }

        # For expanded forms, create reverse mapping to contracted forms
        expanded_to_contraction = {}
        for contraction, variants in contraction_pairs.items():
            for variant in variants:
                if " " in variant:  # Only add expanded forms
                    if variant not in expanded_to_contraction:
                        expanded_to_contraction[variant] = []
                    expanded_to_contraction[variant].append(contraction)

        # Add expanded forms to contraction pairs for lookup
        contraction_pairs.update(expanded_to_contraction)

        # Create alternative forms to search for
        alternatives = [query_lower]

        # Check for contractions in the query
        for contraction, variants in contraction_pairs.items():
            if contraction.lower() in query_lower:
                # Replace the contraction with each alternative
                for variant in variants:
                    alt_query = query_lower.replace(contraction.lower(), variant.lower())
                    if alt_query != query_lower and alt_query not in alternatives:
                        alternatives.append(alt_query)

        logger.info(f"Exact search with {len(alternatives)} alternatives: {alternatives}")

        for msg in messages:
            # Normalize the text to handle Unicode characters
            original_text = msg.get("text", "")
            normalized_text = unicodedata.normalize('NFKD', original_text)
            # Explicitly replace smart apostrophes with standard ASCII apostrophes
            normalized_text = normalized_text.replace('\u2019', "'").replace('\u2018', "'")
            text = normalized_text.lower()

            # Check each alternative form
            for alt_query in alternatives:
                if alt_query in text:
                    logger.info(f"Found match for '{alt_query}' in: '{text[:100]}...'")
                    # Basic scoring based on number of matches and position of first match
                    match_count = text.count(alt_query)
                    position_factor = 1.0 - (text.find(alt_query) / (len(text) + 1)) if text else 0
                    score = weight * (0.6 + 0.2 * match_count + 0.2 * position_factor)
                    # If this isn't the primary query, slightly reduce the score
                    if alt_query != query_lower:
                        score *= 0.9  # Slight penalty for alternative matches
                    results.append((score, msg))
                    break  # Only count each message once, with the first match

        # Sort by score (descending) using only the score value for comparison
        results.sort(key=lambda x: x[0], reverse=True)
        return results

    def _regex_search(self, query: str, messages: list[dict]) -> list[tuple[float, dict]]:
        """Perform regular expression matching."""
        results = []
        weight = self.search_modes.get("regex", {}).get("weight", 1.0)
        regex_options = self.search_modes.get("regex", {}).get("options", {})

        # Normalize the query to handle Unicode characters like smart quotes
        normalized_query = unicodedata.normalize('NFKD', query)
        # Explicitly replace smart apostrophes with standard ASCII apostrophes
        normalized_query = normalized_query.replace('\u2019', "'").replace('\u2018', "'")

        # Special handling for apostrophes to make search more flexible
        contraction_terms = {
            "don't": ["didn't", "don't", "do not", "did not"],
            "didn't": ["don't", "didn't", "did not", "do not"],
            "isn't": ["wasn't", "isn't", "is not", "was not"],
            "wasn't": ["isn't", "wasn't", "was not", "is not"],
            "can't": ["couldn't", "can't", "cannot", "could not"],
            "couldn't": ["can't", "couldn't", "could not", "cannot"],
            "won't": ["wouldn't", "won't", "will not", "would not"],
            "wouldn't": ["won't", "wouldn't", "would not", "will not"]
        }

        # Check if we need special handling for contractions
        flexible_query = normalized_query
        found_contraction = False

        for contraction, alternatives in contraction_terms.items():
            if contraction.lower() in normalized_query.lower():
                # Create a pattern that matches all forms
                parts = []
                for alt in alternatives:
                    if "'" in alt:
                        # For variants with apostrophes, make the apostrophe optional
                        alt_pattern = alt.replace("'", "['']?")
                        parts.append(alt_pattern)
                    else:
                        parts.append(re.escape(alt))

                # Combine alternatives with OR
                pattern_part = "(" + "|".join(parts) + ")"
                flexible_query = re.sub(re.escape(contraction), pattern_part, normalized_query, flags=re.IGNORECASE)
                found_contraction = True
                logger.info(f"Regex search with contraction handling: '{query}' -> '{flexible_query}'")
                break

        if not found_contraction:
            # General handling for any apostrophe
            if "'" in flexible_query:
                # Make apostrophes optional in the pattern
                flexible_query = flexible_query.replace("'", "['']?")
                logger.info(f"Regex search with apostrophe handling: '{query}' -> '{flexible_query}'")
            else:
                logger.info(f"Regex search normalized query: '{query}' -> '{normalized_query}'")

        # Compile the regex pattern
        flags = 0
        if regex_options.get("ignore_case", True):
            flags |= re.IGNORECASE
        if regex_options.get("dot_all", False):
            flags |= re.DOTALL
        if regex_options.get("unicode", True):
            flags |= re.UNICODE

        try:
            # Limit the pattern length for safety
            max_length = regex_options.get("max_pattern_length", 1000)
            if len(flexible_query) > max_length:
                flexible_query = flexible_query[:max_length]

            # First try with the flexible pattern
            pattern = re.compile(flexible_query, flags)

            for msg in messages:
                # Normalize the text to handle Unicode characters
                original_text = msg.get("text", "")
                normalized_text = unicodedata.normalize('NFKD', original_text)
                # Explicitly replace smart apostrophes with standard ASCII apostrophes
                normalized_text = normalized_text.replace('\u2019', "'").replace('\u2018', "'")

                if normalized_text:
                    matches = list(pattern.finditer(normalized_text))
                    if matches:
                        # Score based on number of matches and position of first match
                        match_count = len(matches)
                        first_pos = matches[0].start() / len(normalized_text) if matches else 1.0
                        position_factor = 1.0 - first_pos
                        score = weight * (0.6 + 0.2 * min(match_count, 5) + 0.2 * position_factor)
                        results.append((score, msg))
        except re.error as e:
            # Log the error and fallback to exact search
            logger.warning(f"Invalid regex pattern '{flexible_query}': {str(e)}. Falling back to exact search.")
            return self._exact_search(query, messages)

        # Sort by score (descending) using only the score value for comparison
        results.sort(key=lambda x: x[0], reverse=True)
        return results

    def _hybrid_search(self, query: str, messages: list[dict]) -> list[tuple[float, dict]]:
        """Combine results from exact and regex search methods."""
        # Get weights for each mode
        hybrid_weights = self.config.get('search', {}).get('hybrid_weights', {})
        logger.info(f"Running hybrid search with weights: {hybrid_weights}")

        # Initialize result tracking
        all_results = {}
        msg_scores = defaultdict(float)
        mode_matches = defaultdict(int)

        # Normalize the query to improve matching
        query = query.strip()

        # Run exact search
        if "exact" in self.search_modes and self.search_modes["exact"].get("enabled", False):
            exact_results = self._exact_search(query, messages)
            for score, msg in exact_results:
                msg_id = msg.get("name", "")
                if msg_id:
                    all_results[msg_id] = msg
                    exact_weight = hybrid_weights.get("exact", 1.0)
                    msg_scores[msg_id] += score * exact_weight
                    mode_matches["exact"] += 1
            logger.info(f"Exact search found {mode_matches['exact']} matches")

        # Run regex search
        if "regex" in self.search_modes and self.search_modes["regex"].get("enabled", False):
            regex_results = self._regex_search(query, messages)
            for score, msg in regex_results:
                msg_id = msg.get("name", "")
                if msg_id:
                    all_results[msg_id] = msg
                    regex_weight = hybrid_weights.get("regex", 1.2)
                    msg_scores[msg_id] += score * regex_weight
                    mode_matches["regex"] += 1
            logger.info(f"Regex search found {mode_matches['regex']} matches")

        # Combine and sort results
        combined_results = []
        for msg_id, score in msg_scores.items():
            combined_results.append((score, all_results[msg_id]))

        # Sort by combined score (descending)
        combined_results.sort(key=lambda x: x[0], reverse=True)

        total_matches = len(combined_results)
        logger.info(f"Hybrid search found {total_matches} total unique matches")

        return combined_results
