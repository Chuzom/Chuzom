{{- define "chuzom.name" -}}chuzom{{- end -}}

{{- define "chuzom.fullname" -}}
{{- printf "%s-%s" .Release.Name "chuzom" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "chuzom.labels" -}}
app.kubernetes.io/name: {{ include "chuzom.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{- define "chuzom.selectorLabels" -}}
app.kubernetes.io/name: {{ include "chuzom.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
