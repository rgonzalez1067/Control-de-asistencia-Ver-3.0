// =============================================================================
// Jenkinsfile — Pipeline POST-MERGE de Control de Asistencia
// =============================================================================
// GitLab CI (.gitlab-ci.yml) → valida ANTES del merge   (pre-merge)
// Jenkins (este archivo)     → actúa DESPUÉS del merge  (post-merge)
//
// Flujo de ramas: feature/* | hotfix/* | bugfix/*  →  qa  →  main
//
// Responsabilidades de este pipeline:
//   1. Actualizar tickets en Redmine según la rama destino
//   2. Notificar al equipo SQA cuando hay código listo en QA
//   3. Notificar el cierre de ciclo DevSecOps al llegar a main
//
// Credenciales requeridas (Jenkins › Manage Credentials):
//   redmine-api-key-global  — Secret text con la API key de Redmine
//
// Plugins requeridos:
//   GitLab Plugin, Email Extension, Credentials Binding
// =============================================================================

pipeline {
    agent { label 'gitleaks-owasp-node' }

    parameters {
        string(
            name:         'BRANCH',
            defaultValue: 'qa',
            description:  'Rama destino del merge (qa / main)'
        )
        string(
            name:         'COMMIT',
            defaultValue: '',
            description:  'SHA completo del commit mergeado (opcional)'
        )
    }

    options {
        gitLabConnection('gitlab-connection')
        timestamps()                                           // Muestra hora en cada línea del log
        buildDiscarder(logRotator(numToKeepStr: '30',          // Conserva últimos 30 builds
                                  artifactNumToKeepStr: '10')) // Artefactos: solo los últimos 10
        disableConcurrentBuilds()                              // Evita ejecuciones simultáneas
        timeout(time: 30, unit: 'MINUTES')                    // Corta el pipeline si tarda demasiado
    }

    environment {
        GITLAB_URL   = 'https://gitlab.megasoft.com.ve:8443'
        REDMINE_URL  = 'https://tecnologia.megasoft.com.ve/proyectos/issues'
        PROJECT_NAME = 'Control de Asistencia'
        NOTIFY_EMAIL = 'notificacion_dso@megasoft.com.ve'
        REAL_BRANCH  = "${env.gitlabSourceBranch ?: params.BRANCH}"
        GITLAB_BASE  = 'https://gitlab.megasoft.com.ve:8443/gsi/control-de-asistencia'
        REGISTRY_URL = 'https://gitlab.megasoft.com.ve:8443/gsi/control-de-asistencia/container_registry'
    }

    stages {

        // ====================================================================
        // Inicio — Notifica a GitLab que el pipeline está corriendo
        // ====================================================================
        stage('Inicio') {
            steps {
                updateGitlabCommitStatus name: 'jenkins-post-merge', state: 'running'
                script {
                    def shortCommit = params.COMMIT?.take(8) ?: 'N/A'
                    currentBuild.description = "Branch: ${env.REAL_BRANCH} | Commit: ${shortCommit}"
                }
                echo "==========================================="
                echo " ${env.PROJECT_NAME} — Pipeline Post-Merge"
                echo "==========================================="
                echo " Branch : ${env.REAL_BRANCH}"
                echo " Commit : ${params.COMMIT ?: 'N/A'}"
                echo "==========================================="
            }
        }

        // ====================================================================
        // Actualizar Redmine — Cambia el estado del ticket según la rama
        //
        // qa   → status 6  (Resuelto — pendiente validación SQA)
        // main → status 10 (Cerrado  — ciclo DevSecOps completado)
        //
        // Los IDs de ticket se extraen automáticamente de los mensajes de
        // commit usando los patrones de GitLab: refs #123, #123, feature/123
        // ====================================================================
        stage('Actualizar Redmine') {
            when {
                expression { env.REAL_BRANCH in ['qa', 'main'] }
            }
            steps {
                withCredentials([string(credentialsId: 'redmine-api-key-global',
                                        variable: 'REDMINE_API_KEY')]) {
                    withEnv([
                        "BRANCH_NAME=${env.REAL_BRANCH}",
                        "BUILD_LINK=${env.BUILD_URL}",
                        "GITLAB_BASE=${env.GITLAB_BASE}",
                        "REGISTRY_URL=${env.REGISTRY_URL}",
                        "REDMINE_BASE=${env.REDMINE_URL}",
                        "PROJECT=${env.PROJECT_NAME}",
                    ]) {
                        sh label: 'Actualizar tickets en Redmine', script: '''#!/bin/bash
set -euo pipefail

# --- Datos del commit ---
COMMIT_SHA=$(git rev-parse HEAD)
COMMIT_SHORT=$(git rev-parse --short HEAD)
COMMIT_AUTHOR=$(git log -1 --pretty=%an)
PIPELINE_URL="${GITLAB_BASE}/-/commit/${COMMIT_SHA}/pipelines"
COMMIT_URL="${GITLAB_BASE}/-/commit/${COMMIT_SHA}"

echo "Branch  : ${BRANCH_NAME}"
echo "Commit  : ${COMMIT_SHORT} (${COMMIT_AUTHOR})"
echo "Pipeline: ${PIPELINE_URL}"

# --- Utilidades ---

# Escapa correctamente un string para usarlo como valor JSON
escape_json() {
    python3 -c "import json,sys; sys.stdout.write(json.dumps(sys.stdin.read()))" <<< "$1"
}

# Construye la nota en formato Textile (markup de Redmine)
build_note() {
    local titulo="$1" ambiente="$2" status_text="$3" tickets_list="$4"
    local body
    body=$(cat <<NOTE
h3. ${titulo}

|_. Campo     |_. Valor |
| Proyecto    | ${PROJECT} |
| Rama        | ${BRANCH_NAME} |
| Commit      | "${COMMIT_SHORT}":${COMMIT_URL} |
| Autor       | ${COMMIT_AUTHOR} |
| Ambiente    | ${ambiente} |
| Estado      | ${status_text} |

h4. Referencias

* "Pipeline GitLab":${PIPELINE_URL}
* "Build Jenkins":${BUILD_LINK}
* "Container Registry":${REGISTRY_URL}
NOTE
)
    if [ -n "$tickets_list" ]; then
        body="${body}

h4. Tickets incluidos

${tickets_list}"
    fi
    echo "$body"
}

# Llama a la API de Redmine para actualizar un ticket
update_ticket() {
    local ticket_id="$1" status_id="$2" notes="$3" tracker_id="${4:-}"

    local notes_json
    notes_json=$(escape_json "$notes")

    local issue_obj
    if [ -n "$tracker_id" ]; then
        issue_obj="{\"status_id\":${status_id},\"tracker_id\":${tracker_id},\"notes\":${notes_json}}"
    else
        issue_obj="{\"status_id\":${status_id},\"notes\":${notes_json}}"
    fi

    local http_code
    http_code=$(curl -sk --max-time 30 -w "%{http_code}" \
        -X PUT \
        -H "Content-Type: application/json" \
        -H "X-Redmine-API-Key: $REDMINE_API_KEY" \
        -d "{\"issue\":${issue_obj}}" \
        -o redmine_error.json \
        "${REDMINE_BASE}/${ticket_id}.json")

    if [[ "$http_code" == "200" || "$http_code" == "204" ]]; then
        echo "  ✅ Ticket #${ticket_id} → status ${status_id} (HTTP ${http_code})"
    else
        # Warning, no crítico: el pipeline no debe fallar por un ticket que no existe
        echo "  ⚠️  Ticket #${ticket_id} HTTP ${http_code} — revisar manualmente. Detalles del rechazo:"
        cat redmine_error.json
        echo ""
    fi
}

# Convierte una lista de IDs a enlaces Textile para Redmine
tickets_to_textile() {
    local ids="$1" out=""
    while IFS= read -r tid; do
        [ -z "$tid" ] && continue
        out="${out}* \"#${tid}\":${REDMINE_BASE}/${tid}\n"
    done <<< "$ids"
    printf "%b" "$out"
}

# --- Extraer tickets desde mensajes de commit ---
# Soporta los formatos que GitLab genera: refs #123, #123, feature/123, hotfix/123, bugfix/123
TICKET_PATTERN="refs #[0-9]+|#[0-9]+|feature/[0-9]+|hotfix/[0-9]+|bugfix/[0-9]+"

ALL_TICKET_IDS=$(git log HEAD^1..HEAD --pretty="%s %b" 2>/dev/null \
    | grep -oE "$TICKET_PATTERN" | grep -oE "[0-9]+" | sort -u || true)

# Fallback: buscar solo en el último commit (merge commits con un solo padre)
if [ -z "$ALL_TICKET_IDS" ]; then
    ALL_TICKET_IDS=$(git log -1 --pretty="%s %b" 2>/dev/null \
        | grep -oE "$TICKET_PATTERN" | grep -oE "[0-9]+" | sort -u || true)
fi

if [ -z "$ALL_TICKET_IDS" ]; then
    echo "ℹ️  No se encontraron tickets en el commit. Saltando actualización Redmine."
    exit 0
fi

echo "Tickets detectados: $(echo "$ALL_TICKET_IDS" | tr "\n" " ")"
TICKETS_LIST=$(tickets_to_textile "$ALL_TICKET_IDS")

# --- Configurar parámetros según la rama ---
if [[ "$BRANCH_NAME" == "main" ]]; then
    STATUS_ID=10
    TRACKER_ID=""
    TITULO="Despliegue en Producción"
    AMBIENTE="PROD"
    STATUS_TEXT="Cerrado — ciclo DevSecOps completado"
else
    STATUS_ID=6
    TRACKER_ID=""
    TITULO="Desplegado en QA"
    AMBIENTE="QA"
    STATUS_TEXT="Resuelto — pendiente validación SQA"
fi

NOTES=$(build_note "$TITULO" "$AMBIENTE" "$STATUS_TEXT" "$TICKETS_LIST")

# --- Actualizar cada ticket encontrado ---
for TID in $ALL_TICKET_IDS; do
    update_ticket "$TID" "$STATUS_ID" "$NOTES" "$TRACKER_ID"
done
'''
                    }
                }
            }
        }

        // ====================================================================
        // Notificar SQA — solo cuando llega código a qa
        // ====================================================================
        stage('Notificar SQA') {
            when { expression { env.REAL_BRANCH == 'qa' } }
            steps {
                script {
                    def data         = collectTicketInfo()
                    def ticketLabel  = data.allTickets != 'N/A' ? " [${data.allTickets}]" : ""
                    def shortCommit  = params.COMMIT?.take(8) ?: 'N/A'

                    mail to:      env.NOTIFY_EMAIL,
                         subject: "[QA Ready] ${env.PROJECT_NAME}${ticketLabel} — Listo para validación",
                         body:    """\
El código ha sido mergeado a la rama QA y está disponible para pruebas.

Proyecto : ${env.PROJECT_NAME}
Rama     : qa
Commit   : ${shortCommit}
Tickets  : ${data.allTickets}

Acción requerida:
  Por favor proceder con las pruebas funcionales y de regresión en el ambiente QA.

Build Jenkins : ${env.BUILD_URL}
"""
                    echo "✅  Notificación SQA enviada a ${env.NOTIFY_EMAIL}"
                }
            }
        }

        // ====================================================================
        // Notificar Producción — solo cuando llega código a main
        // ====================================================================
        stage('Notificar Producción') {
            when { expression { env.REAL_BRANCH == 'main' } }
            steps {
                script {
                    def data        = collectTicketInfo()
                    def mergeMsg    = sh(script: 'git log -1 --pretty=%s', returnStdout: true).trim()
                    def ticketLabel = data.allTickets != 'N/A' ? " [${data.allTickets}]" : ""

                    mail to:      env.NOTIFY_EMAIL,
                         subject: "[Producción] ${env.PROJECT_NAME}${ticketLabel} — Release en Main",
                         body:    """\
Código integrado exitosamente en la rama main (producción).

Proyecto : ${env.PROJECT_NAME}
Rama     : main
Merge    : ${mergeMsg}
Tickets  : ${data.allTickets}

Los tickets han sido actualizados automáticamente en Redmine (Cerrado).
El ciclo DevSecOps ha sido completado.

Build Jenkins : ${env.BUILD_URL}
"""
                    echo "✅  Notificación de producción enviada a ${env.NOTIFY_EMAIL}"
                }
            }
        }
    }

    // ========================================================================
    // Post — Acciones finales según resultado del pipeline
    // ========================================================================
    post {
        always {
            echo "Pipeline finalizado — Branch: ${env.REAL_BRANCH} | Estado: ${currentBuild.currentResult}"
        }
        success {
            updateGitlabCommitStatus name: 'jenkins-post-merge', state: 'success'
        }
        unstable {
            // Tests con warnings: marcar como éxito en GitLab para no bloquear el flujo
            updateGitlabCommitStatus name: 'jenkins-post-merge', state: 'success'
            echo "⚠️  Pipeline terminó en estado UNSTABLE — revisar warnings"
        }
        failure {
            updateGitlabCommitStatus name: 'jenkins-post-merge', state: 'failed'
            script {
                // Notificar al autor del commit que causó el fallo
                def devEmail = env.gitlabUserEmail
                    ?: sh(script: 'git log -1 --pretty=%ae', returnStdout: true).trim()

                if (devEmail?.trim()) {
                    mail to:      devEmail,
                         subject: "⚠️ Pipeline FALLIDO — ${env.PROJECT_NAME} (${env.REAL_BRANCH})",
                         body:    """\
El pipeline Post-Merge ha fallado.

Proyecto : ${env.PROJECT_NAME}
Rama     : ${env.REAL_BRANCH}
Commit   : ${params.COMMIT ?: 'N/A'}

Por favor revisa la consola de Jenkins para ver el detalle del error:
${env.BUILD_URL}console
"""
                    echo "Notificación de fallo enviada a ${devEmail}"
                }
            }
        }
    }
}

// =============================================================================
// Helper: Extrae IDs de tickets desde los mensajes de commit
// Soporta: refs #123, #123, feature/123, hotfix/123, bugfix/123
// Retorna: [allTickets: "#45, #67"] o [allTickets: "N/A"]
// =============================================================================
def collectTicketInfo() {
    def raw = sh(
        script: '''
            PATTERN="refs #[0-9]+|#[0-9]+|feature/[0-9]+|hotfix/[0-9]+|bugfix/[0-9]+"
            IDS=$(git log HEAD^1..HEAD --pretty="%s %b" 2>/dev/null \
                | grep -oE "$PATTERN" | grep -oE "[0-9]+" | sort -u || true)
            if [ -z "$IDS" ]; then
                IDS=$(git log -1 --pretty="%s %b" 2>/dev/null \
                    | grep -oE "$PATTERN" | grep -oE "[0-9]+" | sort -u || true)
            fi
            echo "$IDS"
        ''',
        returnStdout: true
    ).trim()

    if (!raw) {
        return [allTickets: 'N/A']
    }

    def formatted = raw.split('\n')
        .findAll { it.trim() }
        .collect { "#${it.trim()}" }
        .join(', ')

    return [allTickets: formatted]
}