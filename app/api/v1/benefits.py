import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_current_claims, get_current_employee, get_tenant_db, require_roles
from app.core.security import TokenClaims
from app.models.approval import ApprovalRequestType\nfrom app.models.benefit import (\n    Benefit,\n    BenefitApplication,\n    BenefitApplicationStatus,\n    BenefitDependent,\n    BenefitPlan,\n)
from app.models.department import Department\nfrom app.models.employee import Employee
from app.models.membership import Role
from app.schemas.benefits import (
    BenefitCreate,
    BenefitDependentCreate,
    BenefitDependentOut,
    BenefitEnd,
    BenefitOut,
    BenefitPlanCreate,
    BenefitPlanOut,
)
from app.services.audit import record_audit_event
from app.services.benefits import (\n    add_dependent,\n    assign_benefit,\n    create_benefit_plan,\n    end_benefit,\n    submit_benefit_application,\n)

router = APIRouter(prefix="/benefits", tags=["benefits"])

_MANAGE = require_roles(Role.ADMIN, Role.PAYROLL_MANAGER, Role.ACCOUNTANT, Role.HR_MANAGER)


@router.post("/plans", response_model=BenefitPlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(
    body: BenefitPlanCreate,
    db: Session = Depends(get_tenant_db),
    claims: TokenClaims = Depends(_MANAGE),
) -> BenefitPlan:
    try:
        plan = create_benefit_plan(
            db,
            org_id=claims.org_id,
            name=body.name,
            frequency=body.frequency,
            description=body.description,
            default_employee_cost_minor=body.default_employee_cost_minor,
            employer_cost_minor=body.employer_cost_minor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a benefit plan with this name already exists",
        ) from exc
    record_audit_event(
        db,
        org_id=claims.org_id,
        account_id=claims.account_id,
        role=claims.role,
        action="benefit_plan.create",
        entity_type="benefit_plan",
        entity_id=plan.id,
        metadata={"name": plan.name},
    )
    return plan


@router.get("/plans", response_model=list[BenefitPlanOut])
def list_plans(
    db: Session = Depends(get_tenant_db), _claims: TokenClaims = Depends(_MANAGE)
) -> list[BenefitPlan]:
    return list(db.scalars(select(BenefitPlan).order_by(BenefitPlan.name)))


@router.post(
    "/employees/{employee_id}", response_model=BenefitOut, status_code=status.HTTP_201_CREATED
)
def assign_employee_benefit(
    employee_id: uuid.UUID,
    body: BenefitCreate,
    db: Session = Depends(get_tenant_db),
    claims: TokenClaims = Depends(_MANAGE),
) -> Benefit:
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="employee not found")

    plan = None
    if body.plan_id is not None:
        plan = db.get(BenefitPlan, body.plan_id)
        if plan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="benefit plan not found"
            )

    try:
        benefit = assign_benefit(
            db,
            org_id=claims.org_id,
            employee_id=employee_id,
            effective_date=body.effective_date,
            plan=plan,
            name=body.name,
            frequency=body.frequency,
            description=body.description,
            value_minor=body.value_minor,
            employer_cost_minor=body.employer_cost_minor,
            end_date=body.end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    record_audit_event(
        db,
        org_id=claims.org_id,
        account_id=claims.account_id,
        role=claims.role,
        action="benefit.assign",
        entity_type="benefit",
        entity_id=benefit.id,
        metadata={"employee_id": str(employee_id), "name": benefit.name},
    )
    return benefit


@router.get("/employees/{employee_id}", response_model=list[BenefitOut])
def list_employee_benefits(
    employee_id: uuid.UUID,
    db: Session = Depends(get_tenant_db),
    _claims: TokenClaims = Depends(_MANAGE),
) -> list[Benefit]:
    return list(db.scalars(select(Benefit).where(Benefit.employee_id == employee_id)))


@router.get("/me", response_model=list[BenefitOut])
def list_my_benefits(
    db: Session = Depends(get_tenant_db), employee: Employee = Depends(get_current_employee)
) -> list[Benefit]:
    return list(db.scalars(select(Benefit).where(Benefit.employee_id == employee.id)))


@router.post("/{benefit_id}/end", response_model=BenefitOut)
def end_employee_benefit(
    benefit_id: uuid.UUID,
    body: BenefitEnd,
    db: Session = Depends(get_tenant_db),
    claims: TokenClaims = Depends(_MANAGE),
) -> Benefit:
    benefit = db.get(Benefit, benefit_id)
    if benefit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="benefit not found")
    try:
        end_benefit(db, benefit, end_date=body.end_date)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.flush()
    record_audit_event(
        db,
        org_id=claims.org_id,
        account_id=claims.account_id,
        role=claims.role,
        action="benefit.end",
        entity_type="benefit",
        entity_id=benefit.id,
    )
    return benefit


@router.post(
    "/employees/{employee_id}/dependents",
    response_model=BenefitDependentOut,
    status_code=status.HTTP_201_CREATED,
)
def add_employee_dependent(
    employee_id: uuid.UUID,
    body: BenefitDependentCreate,
    db: Session = Depends(get_tenant_db),
    claims: TokenClaims = Depends(_MANAGE),
) -> BenefitDependent:
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="employee not found")

    dependent = add_dependent(
        db,
        org_id=claims.org_id,
        employee_id=employee_id,
        full_name=body.full_name,
        relationship=body.relationship,
        date_of_birth=body.date_of_birth,
    )
    record_audit_event(
        db,
        org_id=claims.org_id,
        account_id=claims.account_id,
        role=claims.role,
        action="benefit_dependent.add",
        entity_type="benefit_dependent",
        entity_id=dependent.id,
        metadata={"employee_id": str(employee_id)},
    )
    return dependent


@router.get("/employees/{employee_id}/dependents", response_model=list[BenefitDependentOut])
def list_employee_dependents(
    employee_id: uuid.UUID,
    db: Session = Depends(get_tenant_db),
    _claims: TokenClaims = Depends(_MANAGE),
) -> list[BenefitDependent]:
    return list(
        db.scalars(select(BenefitDependent).where(BenefitDependent.employee_id == employee_id))
    )


@router.get("/me/dependents", response_model=list[BenefitDependentOut])
def list_my_dependents(
    db: Session = Depends(get_tenant_db), employee: Employee = Depends(get_current_employee)
) -> list[BenefitDependent]:
    return list(
        db.scalars(select(BenefitDependent).where(BenefitDependent.employee_id == employee.id))
    )


@router.delete("/dependents/{dependent_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_dependent(
    dependent_id: uuid.UUID,
    db: Session = Depends(get_tenant_db),
    claims: TokenClaims = Depends(_MANAGE),
) -> None:
    dependent = db.get(BenefitDependent, dependent_id)
    if dependent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="dependent not found")
    db.delete(dependent)
    record_audit_event(
        db,
        org_id=claims.org_id,
        account_id=claims.account_id,
        role=claims.role,
        action="benefit_dependent.remove",
        entity_type="benefit_dependent",
        entity_id=dependent_id,
    )



_VIEW_APPLICATIONS = require_roles(
    Role.ADMIN,
    Role.PAYROLL_MANAGER,
    Role.ACCOUNTANT,
    Role.HR_MANAGER,
    Role.MANAGER,
    Role.DEPARTMENT_MANAGER,
    Role.AUDITOR,
)


def _application_or_404(db: Session, application_id: uuid.UUID) -> BenefitApplication:
    application = db.get(BenefitApplication, application_id)
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="benefit application not found"
        )
    return application


@router.get("/plans/available", response_model=list[BenefitPlanOut])
def list_available_benefit_plans(
    db: Session = Depends(get_tenant_db),
    employee: Employee = Depends(get_current_employee),
) -> list[BenefitPlan]:
    return list(
        db.scalars(
            select(BenefitPlan)
            .where(BenefitPlan.org_id == employee.org_id)
            .order_by(BenefitPlan.name)
        )
    )


@router.post(
    "/applications/me",
    response_model=BenefitApplicationOut,
    status_code=status.HTTP_201_CREATED,
)
def apply_for_benefit(
    body: BenefitApplicationCreate,
    db: Session = Depends(get_tenant_db),
    employee: Employee = Depends(get_current_employee),
    claims: TokenClaims = Depends(get_current_claims),
) -> BenefitApplication:
    plan = db.scalar(
        select(BenefitPlan).where(
            BenefitPlan.id == body.plan_id,
            BenefitPlan.org_id == employee.org_id,
        )
    )
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="benefit plan not found")
    try:
        application = submit_benefit_application(
            db,
            org_id=employee.org_id,
            employee_id=employee.id,
            plan=plan,
            requested_effective_date=body.requested_effective_date,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    approvals.get_or_create_instance(
        db,
        org_id=employee.org_id,
        request_type=ApprovalRequestType.BENEFIT_APPLICATION,
        request_id=application.id,
        requester_employee_id=employee.id,
    )
    record_audit_event(
        db,
        org_id=employee.org_id,
        account_id=claims.account_id,
        role=claims.role,
        action="benefit_application.submit",
        entity_type="benefit_application",
        entity_id=application.id,
        metadata={"plan_id": str(plan.id), "plan_name": plan.name},
    )
    return application


@router.get("/applications/me", response_model=list[BenefitApplicationOut])
def list_my_benefit_applications(
    db: Session = Depends(get_tenant_db),
    employee: Employee = Depends(get_current_employee),
) -> list[BenefitApplication]:
    return list(
        db.scalars(
            select(BenefitApplication)
            .where(BenefitApplication.employee_id == employee.id)
            .order_by(BenefitApplication.created_at.desc())
        )
    )


@router.get("/applications", response_model=list[BenefitApplicationOut])
def list_benefit_applications(
    db: Session = Depends(get_tenant_db),
    claims: TokenClaims = Depends(_VIEW_APPLICATIONS),
) -> list[BenefitApplication]:
    query = select(BenefitApplication).order_by(BenefitApplication.created_at.desc())
    if claims.role in {
        Role.ADMIN.value,
        Role.PAYROLL_MANAGER.value,
        Role.ACCOUNTANT.value,
        Role.HR_MANAGER.value,
        Role.AUDITOR.value,
    }:
        return list(db.scalars(query))

    manager = db.scalar(select(Employee).where(Employee.account_id == claims.account_id))
    if manager is None:
        return []
    if claims.role == Role.DEPARTMENT_MANAGER.value:
        department_ids = select(Department.id).where(Department.manager_id == manager.id)
        employee_ids = select(Employee.id).where(Employee.department_id.in_(department_ids))
    else:
        employee_ids = select(Employee.id).where(Employee.manager_id == manager.id)
    return list(db.scalars(query.where(BenefitApplication.employee_id.in_(employee_ids))))


@router.post(
    "/applications/{application_id}/approve", response_model=BenefitApplicationOut
)
def approve_benefit_application(
    application_id: uuid.UUID,
    body: DecisionBody | None = None,
    db: Session = Depends(get_tenant_db),
    claims: TokenClaims = Depends(get_current_claims),
) -> BenefitApplication:
    application = _application_or_404(db, application_id)
    if application.status != BenefitApplicationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="benefit application is not pending"
        )
    try:
        instance, is_final = approvals.decide(
            db,
            claims=claims,
            request_type=ApprovalRequestType.BENEFIT_APPLICATION,
            request_id=application.id,
            requester_employee_id=application.employee_id,
            approve=True,
            comment=body.comment if body else None,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if is_final:
        plan = db.get(BenefitPlan, application.plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="benefit plan no longer exists")
        try:
            benefit = assign_benefit(
                db,
                org_id=application.org_id,
                employee_id=application.employee_id,
                effective_date=application.requested_effective_date,
                plan=plan,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        application.status = BenefitApplicationStatus.APPROVED
        application.benefit_id = benefit.id
        application.decision_note = body.comment if body else None
        application.reviewed_by_account_id = claims.account_id
        application.reviewed_at = datetime.now(UTC)
        db.add(application)

    db.flush()
    record_audit_event(
        db,
        org_id=claims.org_id,
        account_id=claims.account_id,
        role=claims.role,
        action="benefit_application.approve" if is_final else "benefit_application.approve_step",
        entity_type="benefit_application",
        entity_id=application.id,
        metadata={"approval_status": instance.status.value},
    )
    return application


@router.post(
    "/applications/{application_id}/reject", response_model=BenefitApplicationOut
)
def reject_benefit_application(
    application_id: uuid.UUID,
    body: DecisionBody | None = None,
    db: Session = Depends(get_tenant_db),
    claims: TokenClaims = Depends(get_current_claims),
) -> BenefitApplication:
    application = _application_or_404(db, application_id)
    if application.status != BenefitApplicationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="benefit application is not pending"
        )
    try:
        instance, _ = approvals.decide(
            db,
            claims=claims,
            request_type=ApprovalRequestType.BENEFIT_APPLICATION,
            request_id=application.id,
            requester_employee_id=application.employee_id,
            approve=False,
            comment=body.comment if body else None,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    application.status = BenefitApplicationStatus.REJECTED
    application.decision_note = body.comment if body else None
    application.reviewed_by_account_id = claims.account_id
    application.reviewed_at = datetime.now(UTC)
    db.add(application)
    db.flush()
    record_audit_event(
        db,
        org_id=claims.org_id,
        account_id=claims.account_id,
        role=claims.role,
        action="benefit_application.reject",
        entity_type="benefit_application",
        entity_id=application.id,
        metadata={"approval_status": instance.status.value},
    )
    return application
