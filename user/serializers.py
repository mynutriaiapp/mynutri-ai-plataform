from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    """
    Serializer para criação de conta.
    Endpoint: POST /api/v1/auth/register
    Campos esperados: nome (first_name), email, senha (password)
    """
    nome = serializers.CharField(write_only=True)
    email = serializers.EmailField(write_only=True)
    senha = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ('nome', 'email', 'senha')

    def validate_email(self, value):
        """Garante que o e-mail seja único no sistema."""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('Este email já está em uso.')
        return value.lower()

    def create(self, validated_data):
        """Cria o usuário usando os campos mapeados da documentação."""
        user = User.objects.create_user(
            username=validated_data['email'],   # username = email para simplificar
            email=validated_data['email'],
            password=validated_data['senha'],
            first_name=validated_data['nome'],
        )
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer para leitura do perfil do usuário.
    Endpoint: GET /api/v1/user/profile
    """
    nome = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'nome', 'email', 'phone', 'date_of_birth', 'date_joined')

    def get_nome(self, obj):
        return obj.get_full_name() or obj.first_name or obj.email


class UpdateProfileSerializer(serializers.ModelSerializer):
    """
    Serializer para atualização parcial do perfil do usuário.
    Endpoint: PATCH /api/v1/user/profile
    Campos aceitos: first_name, last_name, phone, date_of_birth
    """
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'phone', 'date_of_birth')
        extra_kwargs = {
            'first_name': {'required': False},
            'last_name':  {'required': False},
            'phone':      {'required': False},
            'date_of_birth': {'required': False},
        }
