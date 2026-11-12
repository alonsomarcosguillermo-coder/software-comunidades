from django import forms

from .models import Junta, PuntoOrden

# <input type="datetime-local"> envía "2026-03-10T19:00".
FORMATO_FECHA_HORA = "%Y-%m-%dT%H:%M"


def _fecha_hora(**kwargs) -> forms.DateTimeField:
    return forms.DateTimeField(
        input_formats=[FORMATO_FECHA_HORA],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format=FORMATO_FECHA_HORA),
        **kwargs,
    )


class FormularioJunta(forms.ModelForm):
    primera_convocatoria = _fecha_hora(label="Primera convocatoria")
    segunda_convocatoria = _fecha_hora(label="Segunda convocatoria (opcional)", required=False)

    class Meta:
        model = Junta
        fields = ["tipo", "primera_convocatoria", "segunda_convocatoria", "lugar", "convoca"]


class FormularioPunto(forms.Form):
    titulo = forms.CharField(label="Asunto", max_length=300)
    descripcion = forms.CharField(
        label="Detalle", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )
    mayoria = forms.ChoiceField(
        label="Mayoría", choices=PuntoOrden.Mayoria.choices, initial=PuntoOrden.Mayoria.SIMPLE
    )
    # Desmarcada por defecto: una casilla marcada en las filas vacías haría que el formset
    # las diera por "cambiadas" y exigiera el asunto.
    excepcion_ausentes = forms.BooleanField(
        label="No computa ausentes (excepción del art. 17.8, R-MAY-05)", required=False
    )


# Un formset es una lista de formularios iguales: aquí, un formulario por punto del orden
# del día. Las filas vacías se ignoran; marcar "eliminar" quita el punto.
PuntosFormSet = forms.formset_factory(FormularioPunto, extra=3, can_delete=True)


class FormularioConvocar(forms.Form):
    citacion = forms.DateField(
        label="Fecha de la citación", widget=forms.DateInput(attrs={"type": "date"})
    )
