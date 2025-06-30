import logging
import sys
from fastapi import FastAPI, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, UTC
import json
from pathlib import Path

from reward_engine import RewardEngine, get_reward_engine, logger as reward_engine_logger

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Get logger for this module
logger = logging.getLogger(__name__)

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
    login_streak: int = Field(..., ge=0, description="Number of consecutive days the user has logged in")
    posts_created: int = Field(..., ge=0, description="Number of posts created today")
    comments_written: int = Field(..., ge=0, description="Number of comments written today")
    upvotes_received: int = Field(..., ge=0, description="Number of upvotes received today")
    quizzes_completed: int = Field(..., ge=0, description="Number of quizzes completed today")
    buddies_messaged: int = Field(..., ge=0, description="Number of buddies messaged today")
    karma_spent: int = Field(..., ge=0, description="Amount of karma spent today")
    karma_earned_today: int = Field(..., ge=0, description="Amount of karma earned today")

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
    version="1.0.0",
    debug=True
)

# Add middleware for request logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request: {request.method} {request.url}")
    try:
        response = await call_next(request)
        logger.info(f"Response: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
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

import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.post("/check-surprise-box", response_model=SurpriseBoxResponse)
async def check_surprise_box(request: RewardRequest):
    """
    Check if a user qualifies for a surprise box and calculate the reward details.
    
    - **user_id**: The ID of the user
    - **date**: Date in YYYY-MM-DD format
    - **daily_metrics**: Dictionary containing the user's daily activity metrics
    
    Returns:
        SurpriseBoxResponse: Reward details including qualification status, karma points, and box details.
        
    Raises:
        HTTPException: If there's an error processing the request
    """
    # Validate date format (YYYY-MM-DD)
    try:
        datetime.strptime(request.date, "%Y-%m-%d")
    except ValueError as e:
        error_msg = f"Invalid date format: {request.date}. Expected YYYY-MM-DD"
        logger.error(error_msg)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        ) from e
        
    # Convert daily_metrics to dict
    metrics_dict = request.daily_metrics.dict()
    
    # Log the request
    logger.info(f"Processing request for user {request.user_id} on {request.date}")
    logger.debug(f"Metrics: {metrics_dict}")
    
    try:
        # Get reward engine instance
        reward_engine = get_reward_engine()
        
        # Check for surprise box
        result = reward_engine.check_surprise_box(
            user_id=request.user_id,
            date=request.date,
            daily_metrics=metrics_dict
        )
        
        # Log the result
        # if result.get("surprise_unlocked", False):
        #     logger.info(f"Reward granted to user {request.user_id}: {result}")
        # else:
        #     logger.info(f"No reward for user {request.user_id}: {result.get('reason', 'No reason provided')}")
            
        return result
        
    except ValueError as e:
        error_msg = str(e)
        logger.error(f"Validation error: {error_msg}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        ) from e
    except Exception as e:
        error_msg = "An unexpected error occurred while processing your request"
        logger.error(
            f"{error_msg} for user {request.user_id}",
            exc_info=True,
            extra={"user_id": request.user_id, "date": request.date}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        ) from e

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