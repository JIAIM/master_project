from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"


class MaterialStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"   # розбиття на фрагменти + ембедінги
    INDEXED = "indexed"         # збережено в Chroma
    FAILED = "failed"


class QuestionType(StrEnum):
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class QuestionStatus(StrEnum):
    DRAFT = "draft"                # щойно згенероване
    AI_REJECTED = "ai_rejected"    # Критик відхилив після N спроб
    AI_VERIFIED = "ai_verified"    # Критик схвалив, чекає на викладача
    APPROVED = "approved"          # затверджене людиною
    ARCHIVED = "archived"          # м'яке видалення або замінене новою версією


class QuestionOrigin(StrEnum):
    AI_GENERATED = "ai_generated"
    AI_MODIFIED = "ai_modified"    # змінене ШІ (спростити/ускладнити)
    MANUAL = "manual"              # створене/відредаговане викладачем


class VerificationVerdict(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class SessionStatus(StrEnum):
    LOBBY = "lobby"          # не використовується
    RUNNING = "running"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class ProctoringEventType(StrEnum):
    DISTRACTION_WARNING = "distraction_warning"  # погляд поза екраном довше порогу
    FACE_NOT_DETECTED = "face_not_detected"
    MULTIPLE_FACES = "multiple_faces"
    TAB_HIDDEN = "tab_hidden"                    # перехід на іншу вкладку
    FULLSCREEN_EXIT = "fullscreen_exit"
    CAMERA_DENIED = "camera_denied"                  # студент не дав доступу до камери
    PROCTORING_UNAVAILABLE = "proctoring_unavailable"  # розпізнавання облич не запустилося


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
