from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional
import httpx
from app.api.dependencies import get_current_user

router = APIRouter()


class PaymentRequest(BaseModel):
    """Payment request model"""
    amount: Optional[int] = None
    message: Optional[str] = None
    email: Optional[str] = None
    # Add other fields as needed based on Saweria API requirements


@router.post("/create")
async def create_payment(
    payment_data: Dict[str, Any],
):
    """
    Create payment via Saweria backend
    Proxies request to Saweria payment gateway
    """
    try:
        # Saweria backend URL
        url_payment = "https://backend.saweria.co/donations/snap/b291400e-2cc7-4b32-a642-6e22e2eb8704"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url_payment,
                json=payment_data,
                headers={
                    'Content-Type': 'application/json',
                },
                timeout=30.0
            )
            
            if response.status_code != 200:
                error_detail = response.text
                raise HTTPException(
                    status_code=response.status_code,
                    detail={
                        "error": "Payment request failed",
                        "details": error_detail
                    }
                )
            
            data = response.json()
            return data
            
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail={"error": "Payment gateway timeout", "message": "Request to payment gateway timed out"}
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": "Payment gateway error", "message": str(e)}
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": str(e)}
        )
