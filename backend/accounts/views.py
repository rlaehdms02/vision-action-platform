from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView

from .forms import SignUpForm


class SignUpView(CreateView):
    """회원가입 화면(GET)과 처리(POST). 성공하면 로그인 화면으로 이동."""
    form_class = SignUpForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy("login")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"{self.object.username}님, 가입이 완료되었습니다. 로그인해 주세요.")
        return response
