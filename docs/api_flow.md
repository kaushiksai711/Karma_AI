# Karma Surprise Box API Flow Documentation

This document outlines the complete request processing flow for the Karma Surprise Box API, from receiving an HTTP request to returning a response.

## Table of Contents
0. [Flow Chart](#flow-chart)
1. [Request Entry Point](#1-request-entry-point)
2. [Input Validation](#2-input-validation)
3. [Reward Processing](#3-reward-processing)
   - [3.1 Date Validation](#31-date-validation)
   - [3.2 Reward Eligibility Check](#32-reward-eligibility-check)
   - [3.3 Feature Preparation](#33-feature-preparation)
   - [3.4 Reward Calculation](#34-reward-calculation)
4. [Response Generation](#4-response-generation)
5. [Error Handling](#5-error-handling)


## 0. Flow Chart
[Link](https://www.mermaidchart.com/play?utm_source=mermaid_live_editor&utm_medium=toggle#pako:eNqFk11v2jAUhv_KEb1dJzSmSSCtExCghfKVBNrJ5cJLTopV42S2sw6F_vc5zhethJaLyDrv4_O-9kmyVhCH2Oq1niVN9uA7TwLM0ycbhRI8FKGC1dLzwcXfKSq9g-vrGxiQLeUspBrrerFvYOVhZuUfb0VxmBdPi_gEDnFRp1LA13YbBjT8sLsAf6I6wYgM9xi8QBRLcNKEs6Awe6UyLOmR9RpnfS6RhsdSxNp23HSbVL4f2d05mie8JRMUKHOzMVKzB1XJ3Fq7O6NrmJs747CSGLJAs1iUyJ1FplkjwM13aH_ufqkyTWujWRVpEb8_1rSJfU9GfyhPm5ODm_I60L11m5MxEyHMqQ72TDy_I-aWWGTzlGuWcCwoVFWaRZ1mSTzkGGjwTA8D5l1255DNs6qoX0fwEgxYxAKmjyW4sm5r4mnGOfjMTKJU1k0Ll7hUhPEByk6vTO_Nup7EuolUFJa2q0cc1CgPTCAM4r_gH5Mqn2cBnwwpD1Ju74rKJpVv5c2ZPKPyQEt1Y9VtM3QXqarnubXqA9kk9lMvfgltlqX-YPXHapLVjFAlsVA5VGDFW-mjudg-ROZ2eldRN_qktIxfsHfV6XTOkVmNfLuEPJZIN-peQpz_d5lcQp5E6-0fKShHMw)




## 1. Request Entry Point

The API exposes a single POST endpoint:
- **Endpoint**: `/check-surprise-box`
- **Request Body**: JSON object with the following structure:
  ```json
  {
    "user_id": "string",
    "date": "YYYY-MM-DD",
    "daily_metrics": {
      "login_streak": 0,
      "posts_created": 0,
      "comments_written": 0,
      "upvotes_received": 0,
      "quizzes_completed": 0,
      "buddies_messaged": 0,
      "karma_spent": 0,
      "karma_earned_today": 0
    }
  }
  ```

## 2. Input Validation

1. **Request Body Validation**:
   - FastAPI's Pydantic models validate the request body structure and types
   - All daily metrics must be non-negative integers
   - Date must be in YYYY-MM-DD format

2. **Date Format Validation**:
   - The date string is parsed using `datetime.strptime()`
   - Invalid dates raise a 400 Bad Request error

## 3. Reward Processing

### 3.1 Date Validation
1. The provided date is validated to ensure it's not in the future
2. The date is parsed into a datetime object for further processing

### 3.2 Reward Eligibility Check
1. The system checks if the user has already received a reward for the given date
2. If a reward exists, processing stops and a response indicating the user has already been rewarded is returned

### 3.3 Feature Preparation
1. **Raw Features**: The daily metrics are extracted and normalized
2. **Rule-based Features**: Conditions from `conditions.csv` are evaluated
3. **Temporal Features**: A multiplier is applied based on day of week and month
4. Features are combined into a single feature vector for the ML model

### 3.4 Reward Calculation
1. **Model Prediction**: The ML model predicts the probability of a reward
2. **Threshold Check**: If probability < threshold, return no reward
3. **Box Type Determination**:
   - Rules from `config.json` are evaluated to determine the most appropriate box type
   - Ties are broken using a deterministic seed based on user_id and date
4. **Rarity Calculation**:
   - The rarity (common, rare, elite, legendary) is determined based on box type and prediction probability
   - Uses weighted random selection with adjustments based on prediction confidence
5. **Karma Calculation**:
   - Base karma is determined by box type and rarity
   - Multipliers are applied based on user metrics and temporal factors
   - Final karma is clamped between configured min/max values

## 4. Response Generation

A JSON response is generated with the following structure:

```json
{
  "user_id": "string",
  "surprise_unlocked": true,
  "reward_karma": 0,
  "box_type": "string",
  "box_name": "string",
  "rarity": "string",
  "status": "string",
  "reason": "string"
}
```

## 5. Error Handling

| HTTP Status | Error Code | Description |
|-------------|------------|-------------|
| 400 | INVALID_DATE | Invalid date format or future date |
| 422 | INVALID_FORMAT | Unprocessable Entity |
| 500 | PROCESSING_ERROR | Error during reward processing |

## Database Operations

1. **Check Existing Reward**:
   ```sql
   SELECT * FROM user_rewards WHERE date = ? AND user_id = ?
   ```

2. **Insert New Reward**:
   ```sql
   INSERT INTO user_rewards (user_id, date, box_type)
   VALUES (?, ?, ?)
   ```

## Configuration

The system uses `config.json` for:
- Reward probability threshold
- Karma min/max values
- Box type configurations
- Rarity weights
- Temporal trends and multipliers

## Dependencies

- **ML Model**: `compressed_classifier_bal_1.pkl`
- **Conditions**: `conditions.csv`
- **Database**: SQLite (`karma_rewards.db`)

