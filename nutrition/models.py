from django.db import models
from django.conf import settings


class Anamnese(models.Model):
    """
    Armazena as respostas do questionário nutricional do usuário.
    Cada registro representa uma sessão de anamnese completa.
    Relacionamento: anamnese.user_id → users.id (conforme DATABASE.md)
    """

    GENDER_CHOICES = [
        ('M', 'Masculino'),
        ('F', 'Feminino'),
        ('O', 'Outro'),
    ]

    ACTIVITY_LEVEL_CHOICES = [
        ('sedentary', 'Sedentário'),
        ('light', 'Levemente ativo'),
        ('moderate', 'Moderadamente ativo'),
        ('intense', 'Muito ativo'),
        ('athlete', 'Atleta'),
    ]

    GOAL_CHOICES = [
        ('lose', 'Emagrecimento'),
        ('maintain', 'Manutenção'),
        ('gain', 'Hipertrofia / Ganho de Massa'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='anamneses',
        verbose_name='Usuário',
    )

    # Dados físicos básicos (conforme DATABASE.md e API.md)
    age = models.PositiveIntegerField('Idade')
    gender = models.CharField('Sexo', max_length=1, choices=GENDER_CHOICES)
    weight_kg = models.DecimalField('Peso (kg)', max_digits=5, decimal_places=2)
    height_cm = models.DecimalField('Altura (cm)', max_digits=5, decimal_places=2)

    # Estilo de vida e objetivos
    activity_level = models.CharField(
        'Nível de Atividade', max_length=20, choices=ACTIVITY_LEVEL_CHOICES
    )
    goal = models.CharField('Objetivo', max_length=20, choices=GOAL_CHOICES)
    meals_per_day = models.PositiveIntegerField('Refeições por dia', default=3)

    # Preferências e restrições alimentares
    food_restrictions = models.TextField(
        'Restrições Alimentares',
        blank=True,
        help_text='Ex: vegetariano, sem glúten, sem lactose',
    )
    food_preferences = models.TextField(
        'Preferências Alimentares',
        blank=True,
        help_text='Alimentos que o usuário prefere consumir',
    )
    allergies = models.TextField(
        'Alergias Alimentares',
        blank=True,
        help_text='Ex: amendoim, frutos do mar',
    )

    answered_at = models.DateTimeField('Respondido em', auto_now_add=True)

    class Meta:
        verbose_name = 'Anamnese'
        verbose_name_plural = 'Anamneses'
        ordering = ['-answered_at']

    def __str__(self):
        return f'Anamnese de {self.user} — {self.answered_at.strftime("%d/%m/%Y")}'

    def get_goal_display_pt(self):
        """Retorna o objetivo em português para uso no prompt da IA."""
        return dict(self.GOAL_CHOICES).get(self.goal, self.goal)

    def get_activity_display_pt(self):
        """Retorna o nível de atividade em português para uso no prompt da IA."""
        return dict(self.ACTIVITY_LEVEL_CHOICES).get(self.activity_level, self.activity_level)


class DietPlan(models.Model):
    """
    Armazena o plano alimentar gerado pela IA a partir de uma Anamnese.
    Relacionamentos:
      diet_plans.user_id     → users.id
      diet_plans.anamnese_id → anamnese.id
    (conforme DATABASE.md)
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='diet_plans',
        verbose_name='Usuário',
    )
    anamnese = models.ForeignKey(
        Anamnese,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='diet_plans',
        verbose_name='Anamnese de origem',
    )

    # Resposta bruta da IA em JSON (conforme estrutura definida em PROMPTS.md)
    raw_response = models.JSONField(
        'Resposta da IA (JSON)',
        help_text='JSON completo retornado pela IA conforme estrutura do PROMPTS.md',
    )

    # Campos extraídos do JSON para consulta rápida sem precisar parsear o JSONField
    total_calories = models.PositiveIntegerField(
        'Total de Calorias', null=True, blank=True
    )
    goal_description = models.CharField(
        'Objetivo (descritivo)',
        max_length=100,
        blank=True,
        help_text='Campo "objetivo" retornado pela IA',
    )

    created_at = models.DateTimeField('Gerado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Plano Alimentar'
        verbose_name_plural = 'Planos Alimentares'
        ordering = ['-created_at']

    def __str__(self):
        return f'Plano de {self.user} — {self.created_at.strftime("%d/%m/%Y")} ({self.total_calories} kcal)'


class DietJob(models.Model):
    """
    Rastreia o estado de uma geração de dieta assíncrona via Celery.

    Fluxo de status:
        pending → processing → done
                             ↘ failed

    Endpoints:
        POST /api/v1/diet/generate → cria DietJob (pending) + enfileira task
        GET  /api/v1/diet/status/<id> → frontend faz polling neste endpoint
    """

    STATUS_PENDING    = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_DONE       = 'done'
    STATUS_FAILED     = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING,    'Pendente'),
        (STATUS_PROCESSING, 'Processando'),
        (STATUS_DONE,       'Concluído'),
        (STATUS_FAILED,     'Falhou'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='diet_jobs',
        verbose_name='Usuário',
    )
    anamnese = models.ForeignKey(
        Anamnese,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='diet_jobs',
        verbose_name='Anamnese de origem',
    )
    status = models.CharField(
        'Status',
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    diet_plan = models.OneToOneField(
        DietPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='job',
        verbose_name='Plano gerado',
    )
    error_message = models.TextField('Mensagem de erro', blank=True)
    created_at = models.DateTimeField('Criado em', auto_now_add=True)
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)

    class Meta:
        verbose_name = 'Job de Geração'
        verbose_name_plural = 'Jobs de Geração'
        ordering = ['-created_at']

    def __str__(self):
        return f'DietJob#{self.pk} [{self.status}] — usuário {self.user_id}'


class Meal(models.Model):
    """
    Armazena cada refeição individual de um DietPlan.
    Mapeia diretamente o array "refeicoes" do JSON retornado pela IA (PROMPTS.md).
    Relacionamento: meals.diet_plan_id → diet_plans.id (conforme DATABASE.md)
    """

    diet_plan = models.ForeignKey(
        DietPlan,
        on_delete=models.CASCADE,
        related_name='meals',
        verbose_name='Plano Alimentar',
    )

    # Campos mapeados da estrutura JSON do PROMPTS.md
    meal_name = models.CharField(
        'Nome da Refeição',
        max_length=100,
        help_text='Ex: Café da manhã, Almoço, Jantar',
    )
    description = models.TextField(
        'Descrição',
        help_text='Alimentos e quantidades da refeição',
    )
    calories = models.PositiveIntegerField('Calorias Estimadas')

    # Garante a ordem correta de exibição (café → lanche → almoço → ...)
    order = models.PositiveIntegerField(
        'Ordem de exibição',
        default=0,
        help_text='Posição da refeição dentro do plano (0 = primeira)',
    )

    class Meta:
        verbose_name = 'Refeição'
        verbose_name_plural = 'Refeições'
        ordering = ['diet_plan', 'order']

    def __str__(self):
        return f'{self.meal_name} ({self.calories} kcal) — Plano #{self.diet_plan_id}'
