from fastapi import APIRouter, HTTPException, status, Depends
from app.models.keyword import KeywordCreate, KeywordUpdate, KeywordResponse
from app.services.keyword_service import keyword_service
from app.api.dependencies import get_current_active_user


router = APIRouter(prefix="/keywords", tags=["Keywords"])


@router.get("", response_model=KeywordResponse)
async def get_keywords(current_user: dict = Depends(get_current_active_user)):
    """
    Get current user's keywords
    
    Returns keywords and operator (AND/OR) for the authenticated user
    """
    try:
        result = await keyword_service.get_user_keywords(current_user["id"])
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Keywords not found. Please set your keywords first."
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get keywords: {str(e)}"
        )


@router.post("", response_model=KeywordResponse, status_code=status.HTTP_201_CREATED)
async def set_keywords(
    keyword_data: KeywordCreate,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Set user's keywords (create or update)
    
    - **keywords**: List of 1-3 keywords to monitor
    - **operator**: 'AND' or 'OR' - how to combine keywords in search
    
    If keywords already exist, they will be updated.
    """
    try:
        result = await keyword_service.set_keywords(current_user["id"], keyword_data)
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set keywords: {str(e)}"
        )


@router.patch("", response_model=KeywordResponse)
async def update_keywords(
    keyword_data: KeywordUpdate,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Update user's keywords
    
    - **keywords**: Optional - new list of keywords
    - **operator**: Optional - new operator (AND/OR)
    """
    try:
        result = await keyword_service.update_keywords(current_user["id"], keyword_data)
        return result
        
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update keywords: {str(e)}"
        )


@router.delete("")
async def delete_keywords(current_user: dict = Depends(get_current_active_user)):
    """
    Delete user's keywords
    """
    try:
        result = await keyword_service.delete_keywords(current_user["id"])
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete keywords: {str(e)}"
        )
