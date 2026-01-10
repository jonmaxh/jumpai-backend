from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import User, Category, Email
from app.schemas import CategoryCreate, CategoryUpdate, CategoryResponse
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
async def list_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all categories for the current user with email counts."""
    categories = (
        db.query(Category)
        .filter(Category.user_id == current_user.id)
        .order_by(Category.created_at.desc())
        .all()
    )

    result = []
    for category in categories:
        email_count = (
            db.query(func.count(Email.id))
            .filter(Email.category_id == category.id)
            .scalar()
        )
        cat_dict = {
            "id": category.id,
            "user_id": category.user_id,
            "name": category.name,
            "description": category.description,
            "created_at": category.created_at,
            "email_count": email_count,
        }
        result.append(CategoryResponse(**cat_dict))

    return result


@router.post("", response_model=CategoryResponse)
async def create_category(
    category_data: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new category."""
    existing = (
        db.query(Category)
        .filter(
            Category.user_id == current_user.id,
            Category.name == category_data.name
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="A category with this name already exists"
        )

    category = Category(
        user_id=current_user.id,
        name=category_data.name,
        description=category_data.description,
    )
    db.add(category)
    db.commit()
    db.refresh(category)

    return CategoryResponse(
        id=category.id,
        user_id=category.user_id,
        name=category.name,
        description=category.description,
        created_at=category.created_at,
        email_count=0,
    )


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific category."""
    category = (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == current_user.id)
        .first()
    )

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    email_count = (
        db.query(func.count(Email.id))
        .filter(Email.category_id == category.id)
        .scalar()
    )

    return CategoryResponse(
        id=category.id,
        user_id=category.user_id,
        name=category.name,
        description=category.description,
        created_at=category.created_at,
        email_count=email_count,
    )


@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: int,
    category_data: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a category."""
    category = (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == current_user.id)
        .first()
    )

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    if category_data.name is not None:
        existing = (
            db.query(Category)
            .filter(
                Category.user_id == current_user.id,
                Category.name == category_data.name,
                Category.id != category_id
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="A category with this name already exists"
            )
        category.name = category_data.name

    if category_data.description is not None:
        category.description = category_data.description

    db.commit()
    db.refresh(category)

    email_count = (
        db.query(func.count(Email.id))
        .filter(Email.category_id == category.id)
        .scalar()
    )

    return CategoryResponse(
        id=category.id,
        user_id=category.user_id,
        name=category.name,
        description=category.description,
        created_at=category.created_at,
        email_count=email_count,
    )


@router.delete("/{category_id}")
async def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a category. Emails in this category will be uncategorized."""
    category = (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == current_user.id)
        .first()
    )

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    db.query(Email).filter(Email.category_id == category_id).update(
        {"category_id": None}
    )

    db.delete(category)
    db.commit()

    return {"message": "Category deleted successfully"}
