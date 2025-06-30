import json
import joblib
import numpy as np
import pandas as pd
import random
from datetime import datetime
import hashlib
from typing import Dict,Optional, Any
import re
import logging

# Set up logging
logger = logging.getLogger(__name__)
# Define MODEL_FEATURE_KEYS to ensure consistency
MODEL_FEATURE_KEYS = ["login_streak", "posts_created", "comments_written", "upvotes_received", 
                     "quizzes_completed", "buddies_messaged", "karma_spent", "karma_earned_today"]

class RewardEngine:
    def __init__(self):
        """Initialize the reward engine with the trained model and configurations."""
        self.model = load_model()
        self.conditions = load_conditions()
        self.config = self._load_config()
        # Define expected feature names (raw + rule-based + temporal)
        self.expected_feature_names = MODEL_FEATURE_KEYS + [f"rule_{i}" for i in range(len(self.conditions))] + ["temporal_multiplier"]
        # Initialize database manager for tracking rewarded users
        from db_manager import DatabaseManager
        self.db_manager = DatabaseManager()
        
        # Map box types to their corresponding reasons
        self.box_type_reasons = {
            "streak_engager": "Consistent logins + content and quiz activity",
            "quiz_enthusiast": "Frequent quizzes + regular logins",
            "community_champion": "High-quality posts + community engagement",
            "knowledge_contributor": "Active learning + high karma earned",
            "social_butterfly": "Active messaging + content contributions",
            "balanced_contributor": "Posts and comments + social and karma activity",
            "karma_trader": "Karma spent + karma earned",
            "rising_star": "New user + strong early engagement",
            "creative_scholar": "Creative posts + quiz participation",
            "community_glue": "Community messaging + karma sharing",
            "active_supporter": "Consistent logins + karma contributions",
            "mystery_enthusiast": "Quiz enthusiasm + content creation",
            "quiz_completion": "Quiz completion + learning effort"
        }
    
    def _load_config(self):
        """Load and validate the configuration."""
        with open('config.json', 'r') as f:
            config = json.load(f)
        # Validate required fields
        required_fields = ['reward_probability_threshold', 'reward_rules', 'box_types', 'karma_min', 'karma_max']
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Missing required config field: {field}")
        return config
    
    def _evaluate_rule(self, rule_data, metrics):
        """
        Evaluate if all conditions in a rule are met using the imported functions from Classifier.py
        
        Args:
            rule_data: Either a list of conditions or a dict with 'conditions' key
            metrics: User metrics to evaluate against
            
        Returns:
            bool: True if all conditions are met, False otherwise
        """
        # Handle both old list format and new dict format
        if isinstance(rule_data, dict) and 'conditions' in rule_data:
            conditions = rule_data['conditions']
        elif isinstance(rule_data, list):
            conditions = rule_data
        else:
            conditions = [rule_data]
            
        for condition in conditions:
            try:
                # Skip empty conditions
                if not condition or not str(condition).strip():
                    continue
                    
                # Parse the condition
                parsed = parse_condition(condition)
                if parsed is None:
                    logger.error(f"Failed to parse condition: {condition}")
                    return False
                    
                # Evaluate the condition
                if not check_condition(metrics, parsed):
                    return False
                    
            except Exception as e:
                logger.error(f"Error evaluating condition '{condition}': {str(e)}")
                return False
                
        return True
    def get_temporal_multiplier(self,day_of_week, month):
        """
        Calculate the temporal multiplier based on the day of the week and month.
        
        Args:
            day_of_week (int): Day of the week (0-6)
            month (int): Month of the year (1-12)
        
        Returns:
            float: The temporal multiplier value
        """
        TEMPORAL_TRENDS = self.config["temporal_trends"]
        base_mult = 1.2 if day_of_week in [5, 6] else 1.0
        seasonal_mult = TEMPORAL_TRENDS.get("seasonal_multipliers", {}).get(str(month), 1.0)
        return base_mult * seasonal_mult    
    def _determine_box_type(self, metrics):
        """
        Determine the type of box based on user metrics and reward rules.
        
        Args:
            metrics: Dictionary of user metrics
            
        Returns:
            str: The box type that best matches the user's metrics
        """
        matched_rules = []
        
        # First pass: find all matching rules
        for rule_name, rule_data in self.config['reward_rules'].items():
            if self._evaluate_rule(rule_data, metrics):
                # Store the rule name and its priority (based on number of conditions)
                conditions = rule_data.get('conditions', []) if isinstance(rule_data, dict) else rule_data
                num_conditions = len(conditions) if isinstance(conditions, list) else 1
                matched_rules.append((rule_name, num_conditions))
        
        # If no rules matched, return mystery box
        if not matched_rules:
            return "mystery"
            
        # Sort by number of conditions (more specific rules first)
        matched_rules.sort(key=lambda x: x[1], reverse=True)
        
        # Get all rules with the highest number of conditions
        max_conditions = matched_rules[0][1]
        best_matches = [r for r in matched_rules if r[1] == max_conditions]
        
        # If there's a tie, choose randomly based on a deterministic seed
        if len(best_matches) > 1:
            seed_str = f"{metrics.get('user_id', '')}_{metrics.get('date', '')}"
            seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
            random.seed(seed)
            return random.choice(best_matches)[0]
            
        return best_matches[0][0]
    
    def _calculate_rarity(self, box_type, prediction_probability, seed=None):
        """
        Calculate the rarity of the reward based on probability and box type.
        
        Args:
            box_type: Type of the reward box
            prediction_probability: Model's confidence in the reward (0-1)
            seed: Optional seed for reproducibility
            
        Returns:
            str: Rarity level (common, rare, elite, legendary)
        """
        if box_type not in self.config['box_types']:
            box_type = 'mystery'
            
        box_config = self.config['box_types'][box_type]
        rng = random.Random(seed) if seed is not None else random
        
        # Adjust weights based on prediction probability
        weights = list(box_config['rarity_weights'].values())
        adjusted_weights = [w * (1 + prediction_probability) for w in weights]
        total = sum(adjusted_weights)
        adjusted_weights = [w/total for w in adjusted_weights]
        
        # Select rarity based on weights
        rarities = list(box_config['rarity_weights'].keys())
        return rng.choices(rarities, weights=adjusted_weights, k=1)[0]
    
    def _calculate_reward_karma(self, box_type, rarity, metrics):
        """
        Calculate the karma reward based on box type, rarity, and user metrics.
        
        Args:
            box_type: Type of the reward box
            rarity: Rarity level of the reward
            metrics: Dictionary containing user metrics
            
        Returns:
            int: Calculated karma reward
        """
        if box_type not in self.config['box_types']:
            box_type = 'mystery'
            
        base_karma = self.config['box_types'][box_type]['base_karma']
        
        # Apply rarity multiplier
        rarity_multipliers = {
            'common': 1.0,
            'rare': 1.25,
            'elite': 1.5,
            'legendary': 2.0
        }
        
        # Apply activity bonus (0-50% based on overall activity)
        activity_score = sum(metrics.values()) / len(metrics) if metrics else 0
        activity_bonus = 1.0 + (activity_score / 100) * 0.5
        
        # Calculate final karma
        karma = int(base_karma * rarity_multipliers[rarity] * activity_bonus)
        
        # Ensure karma is within bounds
        return max(self.config['karma_min'], min(self.config['karma_max'], karma))

    def _get_deterministic_seed(self, user_id: str, date: str) -> int:
        """
        Generate a deterministic seed based on user_id and date.
        
        Args:
            user_id (str): The ID of the user
            date (str): The date in YYYY-MM-DD format
            
        Returns:
            int: A deterministic seed value
        """
        seed_str = f"{user_id}_{date}"
        hash_value = hashlib.md5(seed_str.encode()).hexdigest()
        return int(hash_value[:8], 16)
    
    def _prepare_features(self, daily_metrics: Dict[str, Any], date: str) -> np.ndarray:
        """
        Prepare the feature vector for model prediction, including raw, rule-based, and temporal features.
        
        Args:
            daily_metrics (dict): Dictionary of user metrics
            date (str): Date in YYYY-MM-DD format
            
        Returns:
            pd.DataFrame: The prepared feature vector
        """
        # Create DataFrame with raw features and ensure feature names are preserved
        features = {key: [daily_metrics.get(key, 0)] for key in MODEL_FEATURE_KEYS}
        X = pd.DataFrame(features)
        
        # Add rule-based features
        rule_features = np.zeros((1, len(self.conditions)))
        for j, cond in enumerate(self.conditions):
            parsed_condition = parse_condition(cond["condition"])
            rule_features[0, j] = check_condition(daily_metrics, parsed_condition)
        rule_cols = [f"rule_{i}" for i in range(len(self.conditions))]
        rule_df = pd.DataFrame(rule_features, columns=rule_cols, index=X.index)
        X = pd.concat([X, rule_df], axis=1)
        
        # Add temporal feature
        day_dt = datetime.strptime(date, "%Y-%m-%d")
        temporal_mult = self.get_temporal_multiplier(day_dt.weekday(), day_dt.month)
        X["temporal_multiplier"] = temporal_mult
        
        # Ensure correct column order and feature names
        X = X[self.expected_feature_names]
        
        return X
    
    def _find_matching_condition(self, 
                               daily_metrics: Dict[str, Any], 
                               prediction: int,
                               prediction_probability: float) -> Optional[Dict[str, Any]]:
        """
        Find the condition that best matches the user's metrics.
        
        Args:
            daily_metrics (dict): Dictionary of user metrics
            prediction (int): Model prediction (0 or 1)
            prediction_probability (float): Model's confidence in the prediction
            
        Returns:
            dict: The matching condition dictionary, or None if no match found
        """
        # Filter conditions by prediction label
        matching_conditions = [
            cond for cond in self.conditions 
            if cond.get('label') == prediction
        ]
        
        if not matching_conditions:
            return None
        
        # Find all conditions that match the user's metrics
        matched_conditions = []
        for cond in matching_conditions:
            parsed_condition = cond.get('parsed_condition')
            if parsed_condition is None:
                parsed_condition = parse_condition(cond.get('condition', ''))
            if parsed_condition is not None and check_condition(daily_metrics, parsed_condition):
                matched_conditions.append(cond)
        
        if not matched_conditions:
            if prediction == 1:
                # Return the condition with highest probability if no match found but prediction is 1
                return max(matching_conditions, key=lambda x: x.get('probability', 0))
            return None
        
        # Select a condition based on probability weights
        probabilities = [cond.get('probability', 0) for cond in matched_conditions]
        total_prob = sum(probabilities)
        if total_prob > 0:
            probabilities = [p / total_prob for p in probabilities]
        else:
            probabilities = [1.0 / len(matched_conditions)] * len(matched_conditions)
        
        rng = random.Random(self._get_deterministic_seed(
            daily_metrics.get('user_id', ''), 
            daily_metrics.get('date', '')
        ))
        
        return rng.choices(matched_conditions, weights=probabilities, k=1)[0]
    
    def check_surprise_box(self, user_id: str, date: str, daily_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check if a user qualifies for a surprise box and calculate the reward.
        
        Args:
            user_id: The ID of the user
            date: The date of the check (YYYY-MM-DD)
            daily_metrics: Dictionary containing the user's daily metrics
            
        Returns:
            Dictionary containing reward details
        """
        try:
            # Generate deterministic seed for reproducibility
            seed = self._get_deterministic_seed(user_id, date)
            np.random.seed(seed)
            random.seed(seed)
            
            # Add user_id and date to metrics for rule evaluation
            metrics_with_meta = daily_metrics.copy()
            metrics_with_meta.update({
                'user_id': user_id,
                'date': date
            })
            
            # Check if user qualifies for any reward
            box_type = self._determine_box_type(metrics_with_meta)
            
            # Check if user was already rewarded today for this box type
            today = date
            if self.db_manager.is_user_rewarded(today, user_id, box_type):
                return {
                    "user_id": user_id,
                    "surprise_unlocked": False,
                    "status": "already_received",
                    "reason": f"User already received a {box_type} reward today"
                }
            
            # Get prediction probability from model
            features = self._prepare_features(daily_metrics, date)
            prediction_probability = self.model.predict_proba(features)[0][1]
            
            # Check if probability meets threshold
            if prediction_probability < self.config['reward_probability_threshold']:
                return {
                    "user_id": user_id,
                    "surprise_unlocked": False,
                    "status": "missed",
                    "reason": "Activity level below reward threshold"
                }
            
            # Determine reward details
            rarity = self._calculate_rarity(box_type, prediction_probability, seed)
            reward_karma = self._calculate_reward_karma(box_type, rarity, daily_metrics)
            
            # Get box display name
            box_name = self.config['box_types'].get(box_type, {}).get('name', 'Mystery Box')
            
            # Add to rewarded users in database
            self.db_manager.add_rewarded_user(today, user_id, box_type)
            
            # Get the reason based on box type, default to a generic message if not found
            reason = self.box_type_reasons.get(box_type, "For your activity and engagement!")
            
            return {
                "user_id": user_id,
                "surprise_unlocked": True,
                "reward_karma": reward_karma,
                "box_type": box_type,
                "box_name": box_name,
                "rarity": rarity,
                "status": "delivered",
                "reason": reason
            }
            
        except Exception as e:
            logger.error(f"Error in check_surprise_box: {str(e)}")
            return {
                "user_id": user_id,
                "surprise_unlocked": False,
                "status": "error",
                "reason": f"Error processing request: {str(e)}"
            }

def load_model():
    """Load the trained classifier model."""
    try:
        with open('compressed_classifier_bal_1.pkl', 'rb') as f:
            model = joblib.load(f)
            print('model loaded')
        return model
    except Exception as e:
        logger.error(f"Error loading model: {e}")
        return None

def get_reward_engine():
    """Get or create the reward engine singleton."""
    return RewardEngine()
def tokenize_condition(condition_str):
    """
    Tokenize a condition string into a list of tokens for parsing.
    
    Args:
        condition_str (str): The condition string to tokenize (e.g., "login_streak>3")
        
    Returns:
        list: A list of tokens representing the condition components.
        
    Example:
        >>> tokenize_condition("login_streak>3")
        ['login_streak', '>', '3']
    """
    # Pattern to match variables, operators, parentheses, and logical operators
    pattern = r'(\w+)|(>=|<=|==|!=|>|<)|(\(|\))|(and|or|not\b)|(\d+)'
    # Find all matches and filter out empty groups
    tokens = [''.join(match.groups('')).strip() for match in re.finditer(pattern, condition_str)]
    # Filter out empty strings and ensure proper spacing around operators
    result = []
    for token in tokens:
        if token.strip():
            result.append(token.strip())
    return result

def parse_atomic_condition(tokens, start_idx):
    """
    Parse an atomic condition from a list of tokens.
    
    Args:
        tokens (list): List of tokens from tokenize_condition()
        start_idx (int): Starting index in the tokens list
        
    Returns:
        tuple: A tuple containing (parsed_condition, next_index) where:
            - parsed_condition: A tuple (operator, metric, value) or None if parsing fails
            - next_index: The index to continue parsing from
            
    Example:
        >>> parse_atomic_condition(['login_streak', '>', '3'], 0)
        (('>', 'login_streak', 3), 3)
    """
    if start_idx + 2 >= len(tokens):
        return None, start_idx
    var_token = tokens[start_idx]
    op_token = tokens[start_idx + 1]
    val_token = tokens[start_idx + 2]
    if (var_token in MODEL_FEATURE_KEYS and 
        op_token in ['>=', '<=', '==', '<', '>'] and 
        val_token.isdigit()):
        return (var_token, op_token, int(val_token)), start_idx + 3
    return None, start_idx

def parse_condition_recursive(tokens, start_idx=0):
    """
    Recursively parse a condition with possible parentheses and logical operators.
    
    Args:
        tokens (list): List of tokens from tokenize_condition()
        start_idx (int, optional): Starting index in the tokens list. Defaults to 0.
        
    Returns:
        tuple: A tuple containing (parsed_expression, next_index)
        
    Note:
        Supports the following operators: ! (NOT), & (AND), | (OR)
        Handles parenthesized expressions and operator precedence.
    """
    left_expr, idx = parse_term(tokens, start_idx)
    while idx < len(tokens):
        if tokens[idx] == 'or':
            right_expr, idx = parse_condition_recursive(tokens, idx + 1)
            left_expr = ('or', left_expr, right_expr)
        else:
            break
    return left_expr, idx

def parse_term(tokens, start_idx):
    left_expr, idx = parse_factor(tokens, start_idx)
    while idx < len(tokens) and tokens[idx] == 'and':
        right_expr, idx = parse_factor(tokens, idx + 1)
        left_expr = ('and', left_expr, right_expr)
    return left_expr, idx

def parse_factor(tokens, start_idx):
    if start_idx >= len(tokens):
        raise ValueError("Unexpected end of expression")
    if tokens[start_idx] == '(':
        expr, idx = parse_condition_recursive(tokens, start_idx + 1)
        if idx >= len(tokens) or tokens[idx] != ')':
            raise ValueError("Missing closing parenthesis")
        return expr, idx + 1
    else:
        atomic, idx = parse_atomic_condition(tokens, start_idx)
        if atomic is None:
            raise ValueError(f"Invalid atomic condition at position {start_idx}: {tokens[start_idx:start_idx+3]}")
        return atomic, idx

def parse_condition(condition_str):
    """
    Parse a condition string into a parsed expression.
    
    Args:
        condition_str (str): The condition string to parse
    
    Returns:
        tuple: The parsed expression, or None if parsing fails
    """
    if not condition_str.strip():
        return None
    tokens = tokenize_condition(condition_str)
    if not tokens:
        return None
    try:
        expr, _ = parse_condition_recursive(tokens)
        return expr
    except Exception as e:
        logger.error(f"Error parsing condition '{condition_str}': {e}")
        return None

def evaluate_expression(expr, metrics):
    """    
    Evaluate a parsed expression against a dictionary of metrics.
    
    Args:
        expr: The parsed expression (from parse_condition)
        metrics (dict): Dictionary of metric names to values
        
    Returns:
        bool: The boolean result of evaluating the expression
        
    Raises:
        ValueError: If the expression is invalid or contains an unknown operator
        
    Examples:
        >>> evaluate_expression(('>', 'login_streak', 3), {'login_streak': 5})
        True
        >>> evaluate_expression(('and', ('>', 'login_streak', 3), ('>=', 'posts_created', 1)),
        ...                    {'login_streak': 5, 'posts_created': 0})
        False
    """
    if isinstance(expr, tuple) and len(expr) == 3:
        if expr[0] in MODEL_FEATURE_KEYS:
            variable, operator, value = expr
            metric_value = metrics.get(variable, 0)
            if operator == '>=':
                return metric_value >= value
            elif operator == '<=':
                return metric_value <= value
            elif operator == '==':
                return metric_value == value
            elif operator == '<':
                return metric_value < value
            elif operator == '>':
                return metric_value > value
            else:
                raise ValueError(f"Unknown operator: {operator}")
        elif expr[0] == 'and':
            _, left, right = expr
            return evaluate_expression(left, metrics) and evaluate_expression(right, metrics)
        elif expr[0] == 'or':
            _, left, right = expr
            return evaluate_expression(left, metrics) or evaluate_expression(right, metrics)
    raise ValueError(f"Invalid expression: {expr}")

def check_condition(metrics, parsed_condition):
    """
    Check if a parsed condition is satisfied by the given metrics.
    
    Args:
        metrics (dict): Dictionary of metric names to values
        parsed_condition: The parsed condition (from parse_condition)
        
    Returns:
        bool: True if the condition is satisfied, False otherwise or if an error occurs
        
    Note:
        This is a safe wrapper around evaluate_expression that catches and logs any
        exceptions, returning False in case of errors.
    """
    if parsed_condition is None:
        return False
    try:
        return evaluate_expression(parsed_condition, metrics)
    except Exception as e:
        logger.error(f"Error evaluating condition: {e}")
        return False
def load_conditions():
        conditions = []
        with open("conditions.csv", "r") as csvfile:
            reader = pd.read_csv(csvfile)
            for _, row in reader.iterrows():
                parsed_condition = parse_condition(row["condition"])
                if parsed_condition is None:
                    logger.warning(f"Could not parse condition: '{row['condition']}'")
                row_dict = row.to_dict()
                row_dict["parsed_condition"] = parsed_condition
                conditions.append(row_dict)
        return [c for c in conditions if c["parsed_condition"] is not None]
