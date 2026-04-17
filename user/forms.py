"""
Formulários Django — MyNutri AI
================================

ContatoForm: formulário de contato (HTML/HTMX ou API REST).
Aplica a mesma validação robusta de e-mail usada no cadastro.
"""

from django import forms
from django.core.exceptions import ValidationError

from user.email_validation import validate_email_full


class ContatoForm(forms.Form):
    """
    Formulário de contato com validação de e-mail em múltiplas camadas.

    Campos:
      - nome  : nome completo do remetente
      - email : endereço validado (formato + DNS + API opcional)
      - assunto: assunto da mensagem
      - mensagem: corpo da mensagem

    Uso na view:
        form = ContatoForm(request.POST)
        if form.is_valid():
            # form.cleaned_data['email'] é garantidamente válido
            enviar_email_contato(form.cleaned_data)
    """

    nome = forms.CharField(
        max_length=120,
        label='Nome',
        widget=forms.TextInput(attrs={'placeholder': 'Seu nome completo'}),
        error_messages={'required': 'Por favor, informe seu nome.'},
    )

    email = forms.EmailField(
        label='E-mail',
        widget=forms.EmailInput(attrs={'placeholder': 'seu@email.com'}),
        error_messages={
            'required': 'Por favor, informe seu e-mail.',
            'invalid': 'E-mail inválido. Verifique o formato (ex: usuario@dominio.com).',
        },
    )

    assunto = forms.CharField(
        max_length=200,
        label='Assunto',
        widget=forms.TextInput(attrs={'placeholder': 'Assunto da mensagem'}),
        error_messages={'required': 'Por favor, informe o assunto.'},
    )

    mensagem = forms.CharField(
        min_length=10,
        max_length=2000,
        label='Mensagem',
        widget=forms.Textarea(attrs={'rows': 5, 'placeholder': 'Sua mensagem...'}),
        error_messages={
            'required': 'Por favor, escreva sua mensagem.',
            'min_length': 'A mensagem deve ter pelo menos 10 caracteres.',
        },
    )

    def clean_email(self) -> str:
        """Valida o e-mail com formato + DNS + API externa (se configurada)."""
        email = self.cleaned_data.get('email', '').strip().lower()

        result = validate_email_full(email)
        if not result.is_valid:
            raise ValidationError(result.message)

        return email
