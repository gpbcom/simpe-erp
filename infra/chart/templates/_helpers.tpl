{{/*
Shared naming and labelling.

One place, because a label that disagrees with a selector is a Deployment that
manages no pods and reports Ready — the failure mode this file exists to make
impossible.
*/}}

{{- define "simple-erp.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "simple-erp.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "simple-erp.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Labels on every object. `component` is what tells the four processes apart. */}}
{{- define "simple-erp.labels" -}}
app.kubernetes.io/name: {{ include "simple-erp.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{/*
Selector labels for one component.

Deliberately narrow: a selector carrying the chart version would stop matching
its own pods on the next upgrade, and the Deployment would create a second
ReplicaSet while reporting the first as orphaned.
*/}}
{{- define "simple-erp.selectorLabels" -}}
app.kubernetes.io/name: {{ include "simple-erp.name" .root }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/*
The one image, four ways.

Refusing an empty tag rather than defaulting to `latest`: a moving tag makes a
rollback mean "whatever that tag points at now", which is not a rollback.
*/}}
{{- define "simple-erp.image" -}}
{{- $tag := .Values.global.image.tag -}}
{{- if not $tag -}}
{{- fail "global.image.tag must be set — CI sets it to the git SHA. A moving tag is not a rollback target." -}}
{{- end -}}
{{- printf "%s/%s/backend:%s" .Values.global.image.registry .Values.global.image.repository $tag -}}
{{- end -}}

{{- define "simple-erp.frontendImage" -}}
{{- $tag := .Values.global.image.tag -}}
{{- if not $tag -}}
{{- fail "global.image.tag must be set — CI sets it to the git SHA." -}}
{{- end -}}
{{- printf "%s/%s/frontend:%s" .Values.global.image.registry .Values.global.image.repository $tag -}}
{{- end -}}

{{/*
The environment every backend process shares: which configuration file to read,
which logging configuration, and the secrets by reference.

One definition, because the four processes must agree about all of it. They
read the same YAML file, and a worker pointed at a different one would connect
to a different database than the API it serves.
*/}}
{{- define "simple-erp.backendEnv" -}}
- name: SIMPLE_ERP_CONFIG
  value: {{ .Values.global.configFile | quote }}
- name: SIMPLE_ERP_LOGGER
  value: {{ .Values.global.loggerFile | quote }}
{{- end -}}
