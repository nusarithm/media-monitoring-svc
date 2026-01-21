from fastapi import APIRouter, HTTPException, status, Depends
from app.models.settings import ProfileUpdate, UserCreate, UserResponse
from app.core.database import SupabaseServiceClient
from app.core.security import get_password_hash
from app.api.dependencies import get_current_active_user


router = APIRouter(prefix="/settings", tags=["Settings"])


@router.patch("/profile", response_model=UserResponse)
async def update_profile(
    profile_data: ProfileUpdate,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Update user profile
    """
    try:
        supabase = SupabaseServiceClient.get_client()
        user_id = current_user["id"]
        
        # Build update data
        update_data = {}
        if profile_data.name is not None:
            update_data["name"] = profile_data.name
        if profile_data.email is not None:
            # Check if email already exists
            existing = supabase.table("users")\
                .select("id")\
                .eq("email", profile_data.email)\
                .neq("id", user_id)\
                .execute()
            
            if existing.data and len(existing.data) > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )
            
            update_data["email"] = profile_data.email
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No data to update"
            )
        
        # Update user
        result = supabase.table("users")\
            .update(update_data)\
            .eq("id", user_id)\
            .execute()
        
        if not result.data or len(result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        user_data = result.data[0]
        
        return UserResponse(
            id=user_data["id"],
            name=user_data.get("name"),
            email=user_data["email"],
            is_active=user_data["is_active"],
            created_at=user_data["created_at"],
            workspace_id=user_data.get("workspace_id"),
            role_id=user_data.get("role_id")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}"
        )


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace_user(
    user_data: UserCreate,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Create a new user in the same workspace
    """
    try:
        supabase = SupabaseServiceClient.get_client()
        
        # Get current user's workspace
        workspace_id = current_user.get("workspace_id")
        
        # Check if email already exists
        existing = supabase.table("users")\
            .select("id")\
            .eq("email", user_data.email)\
            .execute()
        
        if existing.data and len(existing.data) > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Hash password
        hashed_password = get_password_hash(user_data.password)
        
        # Create user
        new_user = {
            "name": user_data.name,
            "email": user_data.email,
            "password": hashed_password,
            "workspace_id": workspace_id,
            "role_id": user_data.role_id,
            "is_active": True,
            "email_verified": False
        }
        
        result = supabase.table("users")\
            .insert(new_user)\
            .execute()
        
        if not result.data or len(result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user"
            )
        
        user_created = result.data[0]
        
        return UserResponse(
            id=user_created["id"],
            name=user_created.get("name"),
            email=user_created["email"],
            is_active=user_created["is_active"],
            created_at=user_created["created_at"],
            workspace_id=user_created.get("workspace_id"),
            role_id=user_created.get("role_id")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Error creating user: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create user: {str(e)}"
        )


@router.get("/workspace/users", response_model=list[UserResponse])
async def get_workspace_users(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get all users in the same workspace
    """
    try:
        supabase = SupabaseServiceClient.get_client()
        workspace_id = current_user.get("workspace_id")
        
        if not workspace_id:
            return []
        
        result = supabase.table("users")\
            .select("id, name, email, is_active, created_at, workspace_id, role_id")\
            .eq("workspace_id", workspace_id)\
            .order("created_at", desc=True)\
            .execute()
        
        users = []
        for user in result.data:
            users.append(UserResponse(
                id=user["id"],
                name=user.get("name"),
                email=user["email"],
                is_active=user["is_active"],
                created_at=user["created_at"],
                workspace_id=user.get("workspace_id"),
                role_id=user.get("role_id")
            ))
        
        return users
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch workspace users: {str(e)}"
        )
