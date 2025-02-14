"""Routes for db."""

from fastapi import APIRouter, HTTPException

from src.db.utils import connect, get_all_feedback

router = APIRouter()


@router.get("/database")
async def view_database():
    """Returns the contents of the feedback table as JSON."""
    conn = None
    try:
        conn = connect()
        feedback_data = get_all_feedback(conn)
        return feedback_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()
