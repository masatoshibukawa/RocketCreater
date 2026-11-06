"""Local-only manufacturing export API. No print submission endpoint."""

from fastapi import APIRouter
from fastapi.responses import FileResponse

from api.workbench import call
from rocketwright.manufacturing import DEFAULT_PRINT_STORE, PrintRequest, runtime

router = APIRouter(prefix="/manufacturing", tags=["manufacturing"])


@router.get("/runtime")
def print_runtime():
    return runtime()


@router.post("/packages")
def create_package(request: PrintRequest):
    return call(DEFAULT_PRINT_STORE.create, request)


@router.get("/packages/{package_id}/files/{name}")
def download(package_id: str, name: str):
    path = call(DEFAULT_PRINT_STORE.file, package_id, name)
    return FileResponse(path, filename=path.name, headers={"Cache-Control": "no-store"})
