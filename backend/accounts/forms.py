from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class SignUpForm(UserCreationForm):
    """Django 기본 회원가입 폼 + 이메일(선택)."""
    email = forms.EmailField(label="이메일", required=False)

    class Meta:
        model = User
        fields = ("username", "email")
