from fastapi import APIRouter, HTTPException, status, Depends
from app.models.settings import ProfileUpdate, UserCreate, UserResponse
from app.core.database import fetch_one, fetch_all
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
        user_id = current_user["id"]

        if profile_data.name is None and profile_data.email is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No data to update"
            )

        if profile_data.email is not None:
            # Check if email is taken by someone else
            existing = await fetch_one(
                "SELECT id FROM users WHERE email = $1 AND id <> $2",
                profile_data.email, user_id
            )
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )

        # NULL arguments leave the column untouched
        user_data = await fetch_one(
            """
            UPDATE users
               SET name = COALESCE($2, name),
                   email = COALESCE($3, email)
             WHERE id = $1
            RETURNING *
            """,
            user_id, profile_data.name, profile_data.email
        )

        if user_data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

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
        # Get current user's workspace
        workspace_id = current_user.get("workspace_id")

        # Check if email already exists
        existing = await fetch_one(
            "SELECT id FROM users WHERE email = $1", user_data.email
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Hash password
        hashed_password = get_password_hash(user_data.password)

        user_created = await fetch_one(
            """
            INSERT INTO users (name, email, password, workspace_id, role_id, is_active, email_verified)
            VALUES ($1, $2, $3, $4, $5, TRUE, FALSE)
            RETURNING *
            """,
            user_data.name, user_data.email, hashed_password,
            workspace_id, user_data.role_id
        )

        if user_created is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user"
            )

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
        workspace_id = current_user.get("workspace_id")

        if not workspace_id:
            return []

        rows = await fetch_all(
            """
            SELECT id, name, email, is_active, created_at, workspace_id, role_id
              FROM users
             WHERE workspace_id = $1
             ORDER BY created_at DESC
            """,
            workspace_id
        )

        users = []
        for user in rows:
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
