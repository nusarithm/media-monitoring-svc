from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr
from app.services.email_service import email_service
from app.api.dependencies import get_current_active_user


router = APIRouter(prefix="/email", tags=["Email"])


class CheckoutEmailRequest(BaseModel):
    to_email: EmailStr
    name: str
    plan_name: str
    amount: int
    billing_period: str


class PaymentSuccessEmailRequest(BaseModel):
    to_email: EmailStr
    name: str
    plan_name: str
    amount: int
    billing_period: str
    expires_at: str


@router.post("/checkout")
async def send_checkout_email(
    request: CheckoutEmailRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Send checkout confirmation email
    """
    try:
        success = await email_service.send_checkout_email(
            to_email=request.to_email,
            name=request.name,
            plan_name=request.plan_name,
            amount=request.amount,
            billing_period=request.billing_period
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send checkout email"
            )
        
        return {"success": True, "message": "Checkout email sent successfully"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send checkout email: {str(e)}"
        )


@router.post("/payment-success")
async def send_payment_success_email(request: PaymentSuccessEmailRequest):
    """
    Send payment success email (no auth required for webhook)
    """
    try:
        success = await email_service.send_payment_success_email(
            to_email=request.to_email,
            name=request.name,
            plan_name=request.plan_name,
            amount=request.amount,
            billing_period=request.billing_period,
            expires_at=request.expires_at
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send payment success email"
            )
        
        return {"success": True, "message": "Payment success email sent successfully"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send payment success email: {str(e)}"
        )
