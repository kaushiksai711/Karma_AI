from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, UTC
import json
from pathlib import Path

from reward_engine import RewardEngine, get_reward_engine

# App configuration
CONFIG_FILE = Path("config.json")

# Configuration Models
class RewardRule(BaseModel):
    conditions: Union[str, List[str]] = Field(
        ...,
        description="Condition or list of conditions that must be met for this rule"
    )
    description: Optional[str] = Field(
        None,
        description="Human-readable description of this rule"
    )

class BoxTypeConfig(BaseModel):
    name: str = Field(..., description="Display name for this box type")
    base_karma: int = Field(..., ge=1, description="Base karma points for this box type")
    rarity_weights: Dict[str, float] = Field(
        {"common": 0.6, "rare": 0.25, "elite": 0.1, "legendary": 0.05},
        description="Relative weights for each rarity level (will be normalized)"
    )

class ConfigUpdate(BaseModel):
    reward_probability_threshold: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Minimum probability threshold to qualify for a reward"
    )
    karma_min: Optional[int] = Field(
        None,
        ge=1,
        description="Minimum karma that can be awarded"
    )
    karma_max: Optional[int] = Field(
        None,
        ge=1,
        description="Maximum karma that can be awarded"
    )
    reward_rules: Optional[Dict[str, Union[RewardRule, List[str], str]]] = Field(
        None,
        description="Mapping of box type names to their reward rules"
    )
    box_types: Optional[Dict[str, BoxTypeConfig]] = Field(
        None,
        description="Configuration for each box type"
    )

class ConfigResponse(BaseModel):
    reward_probability_threshold: float
    karma_min: int
    karma_max: int
    reward_rules: Dict[str, Any]
    box_types: Dict[str, Any]

# Models
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class User(BaseModel):
    username: str
    disabled: Optional[bool] = None

class UserInDB(User):
    hashed_password: str

class DailyMetrics(BaseModel):
    login_streak: int = 0
    posts_created: int = 0
    comments_written: int = 0
    upvotes_received: int = 0
    quizzes_completed: int = 0
    buddies_messaged: int = 0
    karma_spent: int = 0
    karma_earned_today: int = 0

class RewardRequest(BaseModel):
    user_id: str
    date: str  # Format: YYYY-MM-DD
    daily_metrics: DailyMetrics

class SurpriseBoxResponse(BaseModel):
    user_id: str
    surprise_unlocked: bool
    reward_karma: Optional[int] = None
    reason: Optional[str] = None
    rarity: Optional[str] = None
    box_type: Optional[str] = None
    status: str = "delivered"

class HealthResponse(BaseModel):
    status: str = "ok"

class VersionResponse(BaseModel):
    version: str
    modelVersion: str
    last_updated: str

# Simple user validation function for future use
def validate_user(user_id: str):
    """Placeholder for user validation logic"""
    return True

# Helper functions for configuration management
def load_config() -> Dict[str, Any]:
    """Load the current configuration from file."""
    if not CONFIG_FILE.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuration file not found"
        )
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid configuration file: {str(e)}"
        )

def save_config(config: Dict[str, Any]) -> None:
    """Save the configuration to file."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save configuration: {str(e)}"
        )

def get_reward_engine_dependency() -> RewardEngine:
    """Dependency to get the reward engine instance."""
    return get_reward_engine()

# Initialize FastAPI app
app = FastAPI(
    title="Karma Reward Engine API",
    description="API for Karma Reward Engine that determines surprise box rewards",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize reward engine
reward_engine = get_reward_engine()

# API endpoints

@app.post("/check-surprise-box", response_model=SurpriseBoxResponse)
async def check_surprise_box(request: RewardRequest):
    """
    Check if a user qualifies for a surprise box and calculate the reward details.
    
    - **user_id**: The ID of the user
    - **date**: Date in YYYY-MM-DD format
    - **daily_metrics**: Dictionary containing the user's daily activity metrics
    
    Returns reward details including qualification status, karma points, and box details.
    """
    # Validate date format (YYYY-MM-DD)
    try:
        datetime.strptime(request.date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Expected YYYY-MM-DD"
        )
    try:
        # Convert daily_metrics to dict for the reward engine
        metrics_dict = request.daily_metrics.dict()
        
        # Check for surprise box
        result = reward_engine.check_surprise_box(
            user_id=request.user_id,
            date=request.date,
            daily_metrics=metrics_dict
        )
        
        # Ensure all required fields are present
        if not result.get("user_id"):
            result["user_id"] = request.user_id
        
        result.setdefault("surprise_unlocked", False)
        result.setdefault("reason", "No activity matched")
        result.setdefault("rarity", "common")
        result.setdefault("box_type", "mystery")
        result.setdefault("status", "missed" if not result["surprise_unlocked"] else "delivered")
        
        # Remove any extra fields that might cause issues
        allowed_fields = [
            "user_id", "surprise_unlocked", "reward_karma", "reason",
            "rarity", "box_type", "status"
        ]
        return {k: v for k, v in result.items() if k in allowed_fields}
        
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid input: {str(ve)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing surprise box check: {str(e)}"
        )

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint with system status"""
    return {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
        "service": "Karma Reward Engine",
        "version": "1.0.0"
    }

@app.get("/version", response_model=VersionResponse)
async def version_info():
    """Version information endpoint"""
    return {
        "version": "1.0.0",
        "modelVersion": "1.0",
        "last_updated": "2025-06-20T00:00:00Z"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)