from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Folder, Paper
from app.schemas import FolderCreate, FolderOut, FolderUpdate

router = APIRouter(prefix="/api/folders", tags=["folders"])


@router.get("", response_model=list[FolderOut])
def list_folders(db: Session = Depends(get_db)):
    return db.query(Folder).order_by(Folder.name).all()


@router.post("", response_model=FolderOut, status_code=201)
def create_folder(payload: FolderCreate, db: Session = Depends(get_db)):
    folder = Folder(name=payload.name)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


@router.patch("/{folder_id}", response_model=FolderOut)
def rename_folder(folder_id: int, payload: FolderUpdate, db: Session = Depends(get_db)):
    folder = db.get(Folder, folder_id)
    if folder is None:
        raise HTTPException(404, "Folder not found")
    folder.name = payload.name
    db.commit()
    db.refresh(folder)
    return folder


@router.delete("/{folder_id}", status_code=204)
def delete_folder(folder_id: int, db: Session = Depends(get_db)):
    folder = db.get(Folder, folder_id)
    if folder is None:
        raise HTTPException(404, "Folder not found")
    db.query(Paper).filter(Paper.folder_id == folder_id).update({Paper.folder_id: None})
    db.delete(folder)
    db.commit()
